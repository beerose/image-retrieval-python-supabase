import vecs
import os
import io
import timm
import PIL.Image
from fastapi import FastAPI, UploadFile
from fastapi.responses import HTMLResponse
from matplotlib import pyplot as plt
from storage3 import create_client
import requests
from pydantic import BaseModel
from dotenv import load_dotenv

load_dotenv()

app = FastAPI()

DB_CONNECTION =  os.environ.get("DB_URL", "postgresql://postgres:postgres@localhost:54322/postgres")
COLLECTION_NAME = "images"

SUPABASE_ID = os.environ.get("SUPABASE_ID", "")
STORAGE_URL = f"https://{SUPABASE_ID}.supabase.co/storage/v1"
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "")

print(SUPABASE_KEY, DB_CONNECTION)

headers = {"apiKey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"}
storage_client = create_client(STORAGE_URL, headers, is_async=False)

vx = vecs.create_client(DB_CONNECTION)
images = vx.get_or_create_collection(name=COLLECTION_NAME, dimension=1536)

model = timm.create_model(
    'inception_resnet_v2.tf_in1k',
    pretrained=True,
    num_classes=0,
)
model = model.eval()

def seed():
    data_config = timm.data.resolve_model_data_config(model)
    transforms = timm.data.create_transform(**data_config, is_training=True)

    files = storage_client.from_("images").list()

    for file in files:
        image_url = storage_client.from_("images").get_public_url(file.get("name"))
        response = requests.get(image_url)
        image = PIL.Image.open(io.BytesIO(response.content)).convert("RGB")

        output = model(transforms(image).unsqueeze(0))
        img_emb = output[0].detach().numpy()

        images.upsert(
            [
                (
                    file.get("name"),        
                    img_emb,         
                    {"url": image_url}   
                )
            ]
        )
    print("Upserted images")

    images.create_index()
    print("Created index")

@app.get("/")
async def main():
    content = """
<body>
<form action="/search/" enctype="multipart/form-data" method="post">
<input name="file" type="file" multiple>
<input type="submit">
</form>
</body>
    """
    return HTMLResponse(content=content)

def get_results(image):
    data_config = timm.data.resolve_model_data_config(model)
    transforms = timm.data.create_transform(**data_config, is_training=False)
    
    output = model(transforms(image.convert("RGB")).unsqueeze(0))
    img_emb = output[0].detach().numpy()

    results = images.query(
        img_emb,
        limit=3,
        include_value = True,
        include_metadata = True,
    )

    return results

def plot_results():
    image = PIL.Image.open("./images/test-image.jpg")
    results = get_results(image)

    print(results)
    columns = 3
    rows = results.__len__() // columns + 1
    fig = plt.figure(figsize=(10, 10)) 

    for i in range(0, results.__len__()):
        name, score, metadata = results[i]
        response = requests.get(metadata.get("url"))
        image = PIL.Image.open(io.BytesIO(response.content))
        fig.add_subplot(rows, columns, i + 1) 
  
        plt.imshow(image) 
        plt.axis('off')
        plt.title(f"Caption: {name}\nSimilarity: {1 - score:.2f}")

    plt.show()

class Image(BaseModel):
    name: str
    score: float
    url: str

@app.post("/search/")
def search(file: UploadFile) -> list[Image]:
    contents = file.file.read()
    image = PIL.Image.open(io.BytesIO(contents))

    results = get_results(image)

    images = []
    for name, score, metadata in results:
        images.append(Image(name=name, score=score, url=metadata.get("url")))

    return images

