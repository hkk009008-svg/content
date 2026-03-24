import base64
def get_data_uri(file_path):
    with open(file_path, "rb") as f:
        data = f.read()
    b64 = base64.b64encode(data).decode('utf-8')
    return f"data:image/jpeg;base64,{b64}"
