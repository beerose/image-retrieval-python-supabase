import vecs
import os
import io
import timm
from PIL import Image
from fastapi import FastAPI, UploadFile
from fastapi.responses import HTMLResponse, FileResponse
from matplotlib import pyplot as plt, image as mpimg

app = FastAPI()

DB_CONNECTION = "postgresql://postgres:postgres@localhost:54322/postgres"
COLLECTION_NAME = "vectors_11"
IMAGES_PATH = "../images/"

vx = vecs.create_client(DB_CONNECTION)
images = vx.get_collection(name=COLLECTION_NAME)

model = timm.create_model(
    'inception_resnet_v2.tf_in1k',
    pretrained=True,
    num_classes=0,
)
model = model.eval()

def seed():
    data_config = timm.data.resolve_model_data_config(model)
    transforms = timm.data.create_transform(**data_config, is_training=True)

    contents = os.listdir(IMAGES_PATH)
    for content in contents:
        output = model(transforms(Image.open(IMAGES_PATH + content).convert('RGB')).unsqueeze(0))
        img_emb = output[0].detach().numpy()

        images.upsert(
            [
                (
                    content,        
                    img_emb,         
                    {"type": "png"}   
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
        include_value = True,
    )

    return results

def plot_results(results):
    image = Image.open(IMAGES_PATH + 'test.png')
    results = get_results(image)

    print(results)
    columns = 3
    rows = results.__len__() // columns + 1
    fig = plt.figure(figsize=(10, 10)) 

    for i in range(0, results.__len__()):
        name, score = results[i]
        image = mpimg.imread('./images/' + name)
        fig.add_subplot(rows, columns, i + 1) 
  
        plt.imshow(image) 
        plt.axis('off')
        plt.title(f"Caption: {name}\nSimilarity: {1 - score:.2f}")

    plt.show()

@app.post("/search/")
def search(file: UploadFile):
    contents = file.file.read()

    image = Image.open(io.BytesIO(contents))
    results = get_results(image)

    return FileResponse(IMAGES_PATH + results[0][0], media_type="image/png")

