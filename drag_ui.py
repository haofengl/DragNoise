import os
import gradio as gr

from utils.ui_utils import get_points, undo_points
from utils.ui_utils import clear_all, store_img, train_lora_interface, run_drag
from utils.ui_utils import clear_all_gen, store_img_gen

LENGTH=480 # length of the square area displaying/editing images

with gr.Blocks(title='DragNoise', theme=gr.themes.Monochrome()) as demo:
    # layout definition
    with gr.Row():
        gr.Markdown("""
        #  Official Implementation of [DragNoise](https://github.com/haofengl/DragNoise)
        """)

    # UI components for editing images
    with gr.Tab(label=''):
        mask = gr.State(value=None) # store mask
        selected_points = gr.State([]) # store points
        original_image = gr.State(value=None) # store original input image
        with gr.Row():
            with gr.Column():
                canvas = gr.Image(type="numpy", tool="sketch", label="Draw Mask",
                    show_label=True, height=LENGTH, width=2*LENGTH) # for mask painting

            with gr.Column():
                input_image = gr.Image(type="numpy", label="Click Points",
                    show_label=True, height=LENGTH, width=LENGTH) # for points clicking

            with gr.Column():
                output_image = gr.Image(type="numpy", label="Editing Results",
                    show_label=True, height=LENGTH, width=LENGTH)


        with gr.Row():
            undo_button = gr.Button("Undo point")
            run_button = gr.Button("Run")


        # general parameters
        with gr.Row():
            prompt = gr.Textbox(label="Prompt")
            lora_path = gr.Textbox(value="./lora_tmp", label="LoRA path")
            lora_status_bar = gr.Textbox(label="display LoRA training status")
            train_lora_button = gr.Button(value='Train LoRA', scale=0.3)

        # algorithm specific parameters
        with gr.Tab("Drag Config"):
            with gr.Row():
                n_pix_step = gr.Number(
                    value=60,
                    label="Maximum Number of Iterations",
                    precision=0)
                inversion_strength = gr.Number(value=0.7, label='Initial Timestep')
                end_step = gr.Number(value=0, label='End Timestep')
                lam = gr.Number(value=0.1, label="Lambda")
                latent_lr = gr.Number(value=0.01, label="Learning Rate")
                start_step = gr.Number(value=0, label="start_step", precision=0, visible=False)
                start_layer = gr.Number(value=10, label="start_layer", precision=0, visible=False)

        with gr.Tab("Base Model Config"):
            with gr.Row():
                local_models_dir = '/media/haofeng/w/AIGC/DragDiffusion/local_pretrained_models'
                local_models_choice = \
                    [os.path.join(local_models_dir,d) for d in os.listdir(local_models_dir) if os.path.isdir(os.path.join(local_models_dir,d))]
                model_path = gr.Dropdown(value="runwayml/stable-diffusion-v1-5",
                    label="Diffusion Model Path",
                    choices=[
                        "runwayml/stable-diffusion-v1-5",
                    ] + local_models_choice
                )
                vae_path = gr.Dropdown(value="default",
                    label="VAE choice",
                    choices=["default",
                    "stabilityai/sd-vae-ft-mse"] + local_models_choice
                )

        with gr.Tab("LoRA Parameters"):
            with gr.Row():
                lora_step = gr.Number(value=60, label="LoRA training steps", precision=0)
                lora_lr = gr.Number(value=0.0005, label="LoRA learning rate")
                lora_batch_size = gr.Number(value=4, label="LoRA batch size", precision=0)
                lora_rank = gr.Number(value=16, label="LoRA rank", precision=0)

        with gr.Row():
            gr.Markdown("""
            #  Guideline
            * DragNoise features semantic editing and generally does not require the use of a Draw Mask.
            * First, select the local Stable Diffusion Model in the Base Model Config section, and then train LoRA, which is essential.
            * The Maximum Number of Iterations indicates the maximum iteration steps for image editing. If it's a long-distance editing operation, you can increase this value appropriately.
            * The Learning Rate represents the rate of latent update during the editing process. If it's a long-distance editing operation, you can increase this value appropriately.
            * Lambda represents the weight of retaining the original image during the editing process. If the editing result is significantly distorted, you can increase this value appropriately.
            * The Initial Timestep indicates the degree of DDIM inversion. If you want to control significant changes in objects, you can increase this value appropriately.
            * The End Timestep indicates the end time step of denoise propagation in the editing result. If you want to enhance image detail characteristics, you can increase this value to 10.
            """)



    # event definition
    # event for dragging user-input real image
    canvas.edit(
        store_img,
        [canvas],
        [original_image, selected_points, input_image, mask]
    )
    input_image.select(
        get_points,
        [input_image, selected_points],
        [input_image],
    )
    undo_button.click(
        undo_points,
        [original_image, mask],
        [input_image, selected_points]
    )
    train_lora_button.click(
        train_lora_interface,
        [original_image,
        prompt,
        model_path,
        vae_path,
        lora_path,
        lora_step,
        lora_lr,
        lora_batch_size,
        lora_rank],
        [lora_status_bar]
    )
    run_button.click(
        run_drag,
        [original_image,
        input_image,
        mask,
        prompt,
        selected_points,
        inversion_strength,
        end_step,
        lam,
        latent_lr,
        n_pix_step,
        model_path,
        vae_path,
        lora_path,
        start_step,
        start_layer,
        ],
        [output_image]
    )



demo.queue().launch(share=True, debug=True)
