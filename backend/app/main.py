from fastapi import FastAPI

app = FastAPI(title="Proof-of-Action API")


@app.get("/health")
def health():
    return {"status": "ok"}
