import os
import replicate
import uuid
import requests
from replicate.exceptions import ReplicateError
from IPython.display import Image, display
from dotenv import load_dotenv

load_dotenv()

REPLICATE_API_KEY = os.getenv("REPLICATE_API_KEY")
REPLICATE_USERNAME = "sundai-club"
FINETUNED_MODEL_NAME = "redbull_suzuka_livery"
TRIGGER_WORD = "tr1gg3r_w0rd"

os.environ["REPLICATE_API_TOKEN"] = REPLICATE_API_KEY

# -------------------- Model Respository --------------------
def create_or_get_model():
    replicate_username = REPLICATE_USERNAME
    finetuned_model_name = FINETUNED_MODEL_NAME

    try:
        model = replicate.models.create(
            owner=replicate_username,
            name=finetuned_model_name,
            visibility="public",  # or "private" if you prefer
            hardware="gpu-t4",    # Replicate will override this for fine-tuned models
            description="A fine-tuned FLUX.1 model",
        )
        print(f"Model created: {model.name}")
    except ReplicateError as e:
        if "already exists" in e.detail:
            print("Model already exists, loading it.")
            model = replicate.models.get(f"{replicate_username}/{finetuned_model_name}")
        else:
            raise e

    print(f"Model URL: https://replicate.com/{model.owner}/{model.name}")
    return model

# -------------------- Training --------------------
def train_model(model):
    dataset_path = "dataset.zip"
    steps = 1000 # keep the number of steps at 1000

    training = replicate.trainings.create(
        version="ostris/flux-dev-lora-trainer:26dce37af90b9d997eeb970d92e47de3064d46c300504ae376c75bef6a9022d2",
        input={
            "input_images": open(dataset_path, "rb"),
            "steps": steps,
        },
        trigger_word=TRIGGER_WORD,
        destination=f"{model.owner}/{model.name}"
    )

    print(f"Training started: {training.status}")
    print(f"Training URL: https://replicate.com/p/{training.id}")

def test_model(model):
    latest_version = model.versions.list()[0]

    output = replicate.run(
        latest_version,
        input={
            "prompt": f"{TRIGGER_WORD}",
            "guidance_scale": 10,     # how much attention the model pays to the prompt. Try different values between 1 and 50 to see
            "model": "dev",            # after fine-tuning you can use "schnell" model to generate images faster. In that case put num_inference_steps=4
        }
    )

    generated_img_url = str(output[0])
    print(f"Generated image URL: {generated_img_url}")
    display(Image(url=generated_img_url))

# -------------------- Mastodon --------------------
def generate_image_post(text = ""):
    if text:
        text += "\n\n*This post was AI generated.*"
    else:
        text += "*This post was AI generated.*"

    output = replicate.run(
        "sundai-club/redbull_suzuka_livery:24b0b168263d9b15ce91d2e3eeb44958c770602c408a0c947f9d78b8d1fac737",
        input={
            "model": "dev",
            "prompt": f"{TRIGGER_WORD} on track f1",
            "go_fast": False,
            "lora_scale": 1,
            "megapixels": "1",
            "num_outputs": 1,
            "aspect_ratio": "1:1",
            "output_format": "webp",
            "guidance_scale": 3,
            "output_quality": 80,
            "prompt_strength": 0.8,
            "extra_lora_scale": 1,
            "num_inference_steps": 28
        }
    )

    image_url = output[0]
    filename = f"{uuid.uuid4()}.webp"
    image_path = filename

    resp = requests.get(image_url)
    resp.raise_for_status()

    with open(image_path, "wb") as f:
        f.write(resp.content)

    return {
        "type": "image",
        "payload": (text, image_path)
    }

if __name__ == "__main__":
    # model = create_or_get_model()
    # train_model(model)
    # test_model(model)
    pass
