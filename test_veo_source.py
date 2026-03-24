from google.genai import types
source = types.GenerateVideosSource(
    prompt="Smooth pan. Cinematic lighting.",
    image=types.Image(gcs_uri="gs://test/image.jpg")
)
print(source)
