from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, conint, confloat
import torch
from typing import List, Dict, Any

app = FastAPI(title="Admissions Predictor API", version="1.0.0")

MODEL_PATH = "admissions_model_full.pt"

# Load model 
try:
    model = torch.load(MODEL_PATH, map_location="cpu", weights_only=False)
    model.eval()
except Exception as e:
    model = None
    model_load_error = e
else:
    model_load_error = None


class AdmissionInput(BaseModel):
    gre: confloat(ge=0, le=800)   # GRE score 0-800
    gpa: confloat(ge=0, le=4)     # GPA 0-4
    rank: conint(ge=1, le=4)      # Rank 1-4


class AdmissionOutput(BaseModel):
    pred: int
    prob: float
    inputs_normalized: List[float]


@app.get("/health")
def health() -> Dict[str, Any]:
    if model is None:
        return {
            "status": "error",
            "detail": f"Model failed to load: {repr(model_load_error)}"
        }
    return {"status": "ok"}


@app.post("/predict", response_model=AdmissionOutput)
def predict(payload: AdmissionInput) -> AdmissionOutput:
    if model is None:
        raise HTTPException(
            status_code=500,
            detail=f"Model not available: {repr(model_load_error)}"
        )

    # Normalize features
    gre_norm = float(payload.gre) / 800.0
    gpa_norm = float(payload.gpa) / 4.0


    if payload.rank == 1:
        rank_oh = [1.0, 0.0, 0.0]
    elif payload.rank == 2:
        rank_oh = [0.0, 1.0, 0.0]
    elif payload.rank == 3:
        rank_oh = [0.0, 0.0, 1.0]
    else:  # rank == 4
        rank_oh = [0.0, 0.0, 0.0]

    features = [gre_norm, gpa_norm] + rank_oh

    tensor = torch.tensor(features, dtype=torch.float32)

    with torch.no_grad():
        out = model(tensor)
        prob_val = float(out.squeeze().item())

    pred = 1 if prob_val >= 0.5 else 0

    return AdmissionOutput(
        pred=pred,
        prob=prob_val,
        inputs_normalized=features
    )