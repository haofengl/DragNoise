import copy
import time
import math

import numpy as np
import torch
import torch.nn.functional as F
# import copy

from torch.utils.tensorboard import SummaryWriter


def point_tracking(F0,
                   F1,
                   handle_points,
                   handle_points_init,
                   args):
    with torch.no_grad():
        for i in range(len(handle_points)):
            pi0, pi = handle_points_init[i], handle_points[i]
            f0 = F0[:, :, int(pi0[0]), int(pi0[1])]

            r1, r2 = int(pi[0])-args.r_p, int(pi[0])+args.r_p+1
            c1, c2 = int(pi[1])-args.r_p, int(pi[1])+args.r_p+1
            F1_neighbor = F1[:, :, r1:r2, c1:c2]
            all_dist = (f0.unsqueeze(dim=-1).unsqueeze(dim=-1) - F1_neighbor).abs().sum(dim=1)
            all_dist = all_dist.squeeze(dim=0)
            # WARNING: no boundary protection right now
            row, col = divmod(all_dist.argmin().item(), all_dist.shape[-1])
            handle_points[i][0] = pi[0] - args.r_p + row
            handle_points[i][1] = pi[1] - args.r_p + col
        return handle_points

def check_handle_reach_target(handle_points,
                              target_points):
    # dist = (torch.cat(handle_points,dim=0) - torch.cat(target_points,dim=0)).norm(dim=-1)
    all_dist = list(map(lambda p,q: (p-q).norm(), handle_points, target_points))
    return (torch.tensor(all_dist) < 2.0).all()

# obtain the bilinear interpolated feature patch centered around (x, y) with radius r
def interpolate_feature_patch(feat,
                              y,
                              x,
                              r):
    x0 = torch.floor(x).long()
    x1 = x0 + 1

    y0 = torch.floor(y).long()
    y1 = y0 + 1

    wa = (x1.float() - x) * (y1.float() - y)
    wb = (x1.float() - x) * (y - y0.float())
    wc = (x - x0.float()) * (y1.float() - y)
    wd = (x - x0.float()) * (y - y0.float())

    Ia = feat[:, :, y0-r:y0+r+1, x0-r:x0+r+1]
    Ib = feat[:, :, y1-r:y1+r+1, x0-r:x0+r+1]
    Ic = feat[:, :, y0-r:y0+r+1, x1-r:x1+r+1]
    Id = feat[:, :, y1-r:y1+r+1, x1-r:x1+r+1]

    return Ia * wa + Ib * wb + Ic * wc + Id * wd

def drag_diffusion_update(model,
                          init_code,
                          t,
                          handle_points,
                          target_points,
                          mask,
                          args):

    assert len(handle_points) == len(target_points), \
        "number of handle point must equals target points"

    text_emb = model.get_text_embeddings(args.prompt).detach()
    # the init output feature of unet
    with torch.no_grad():
        unet_output, F0 , h_feature = model.forward_unet_features(init_code, t, encoder_hidden_states=text_emb,
            layer_idx=args.unet_feature_idx, interp_res_h=args.sup_res_h, interp_res_w=args.sup_res_w)
        x_prev_0,_ = model.step(unet_output, t, init_code)



    # prepare optimizable init_code and optimizer
    # init_code.requires_grad_(True)
    # optimizer = torch.optim.Adam([init_code], lr=args.lr)
    h_feature.requires_grad_(True)
    optimizer = torch.optim.Adam([h_feature], lr=args.lr)


    # prepare for point tracking and background regularization
    handle_points_init = copy.deepcopy(handle_points)
    interp_mask = F.interpolate(mask, (init_code.shape[2],init_code.shape[3]), mode='nearest')

    h_features = []

    loss_list = []
    new_target = []
    point = []

    for i in range(len(handle_points)):
        pi, ti = handle_points[i], target_points[i]
        point.append(pi)
        point.append(ti)

    # prepare amp scaler for mixed-precision training
    scaler = torch.cuda.amp.GradScaler()
    for step_idx in range(args.n_pix_step):

        with torch.autocast(device_type='cuda', dtype=torch.float16):
            unet_output, F1, h_feature = model.forward_unet_features(init_code, t, encoder_hidden_states=text_emb,  h_feature=h_feature,
                layer_idx=args.unet_feature_idx, interp_res_h=args.sup_res_h, interp_res_w=args.sup_res_w)
            x_prev_updated,_ = model.step(unet_output, t, init_code)

            copy_h = copy.deepcopy(h_feature)
            h_features.append(copy_h)

            # do point tracking to update handle points before computing motion supervision loss
            if step_idx != 0:
                handle_points = point_tracking(F0, F1, handle_points, handle_points_init, args)
                print('{} _ new handle points:{}'.format(step_idx, handle_points) )

            # break if all handle points have reached the targets
            if check_handle_reach_target(handle_points, target_points):
                break

            loss = 0.0
            for i in range(len(handle_points)):
                pi, ti = handle_points[i], target_points[i]

                pii = pi.tolist()
                new_target.append(pii)

                # skip if the distance between target and source is less than 1
                if (ti - pi).norm() < 2.:
                    continue

                di = (ti - pi) / (ti - pi).norm()

                # motion supervision
                f0_patch = F1[:,:,int(pi[0])-args.r_m:int(pi[0])+args.r_m+1, int(pi[1])-args.r_m:int(pi[1])+args.r_m+1].detach()
                f1_patch = interpolate_feature_patch(F1, pi[0] + di[0], pi[1] + di[1], args.r_m)
                loss += ((2*args.r_m+1)**2)*F.l1_loss(f0_patch, f1_patch)

            # masked region must stay unchanged
            loss += args.lam * ((x_prev_updated-x_prev_0)*(1.0-interp_mask)).abs().sum()
            loss_list.append(loss)

            # loss += args.lam * ((init_code_orig-init_code)*(1.0-interp_mask)).abs().sum()
            print('loss total=%f'%(loss.item()))

        scaler.scale(loss).backward()
        scaler.step(optimizer)
        scaler.update()
        optimizer.zero_grad()


    return init_code, h_feature, h_features
