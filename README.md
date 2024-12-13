# wikipedia-api

0. Clone the repository
```sh
git clone --recurse-submodules https://github.com/Datata1/wikipedia-api
``

1. Create a virtual environment
```sh
python -m venv .venv
```

2. Activate the virtual environment
```sh
source .venv/bin/activate
```

3. Install the dependencies
```sh
pip install -r requirements.txt
```

4. Download the model
```sh
wget -P ./llama.cpp/models https://huggingface.co/bartowski/Llama-3.2-1B-Instruct-GGUF/resolve/main/Llama-3.2-1B-Instruct-Q5_K_M.gguf
```

5. build Llama.cpp
```sh
cd llama.cpp
cmake -B build
cmake --build build --config Release
```

6. start uvicorn
```sh
uvicorn main:app --reload
```

7. Open the browser and go to http://127.0.0.1:8000
