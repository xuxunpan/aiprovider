import client from "./client";

export interface GenerateResponse {
  task_id: string;
  status: string;
  image_url: string;
  credits: number;
}

export async function generateImage(prompt: string, image: File): Promise<GenerateResponse> {
  const form = new FormData();
  form.append("prompt", prompt);
  form.append("image", image);
  const { data } = await client.post<GenerateResponse>("/images/generate", form);
  return data;
}

export async function recharge(): Promise<{ ok: boolean; message: string }> {
  const { data } = await client.post("/credits/recharge");
  return data;
}
