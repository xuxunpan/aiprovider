from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from app.services import openai_client, storage

router = APIRouter(prefix="/internal", tags=["generate"])


@router.post("/generate")
async def generate(
    user_id: str = Form(...),
    prompt: str = Form(...),
    image: UploadFile = File(...),
):
    image_bytes = await image.read()
    if not image_bytes:
        raise HTTPException(status_code=400, detail="empty image")

    try:
        result_bytes = await openai_client.edit_image(
            prompt=prompt,
            image_bytes=image_bytes,
            filename=image.filename or "input.png",
        )
    except openai_client.OpenAIError as exc:
        raise HTTPException(status_code=502, detail=f"openai error: {exc}")

    image_path = storage.save_image(user_id, result_bytes, ext="png")
    return {"image_path": image_path}
