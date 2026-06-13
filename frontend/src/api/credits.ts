import client from "./client";

export interface RechargeRecord {
  id: string;
  amount_credits: number;
  price: number;
  status: string;
  created_at: string;
}

export async function getCredits(): Promise<{ credits: number }> {
  const { data } = await client.get("/credits");
  return data;
}

export async function getRechargeRecords(): Promise<{ records: RechargeRecord[] }> {
  const { data } = await client.get<{ records: RechargeRecord[] }>("/credits/records");
  return data;
}

export async function createRechargeRecord(amount: number, price: number): Promise<{ ok: boolean; record_id: string }> {
  const { data } = await client.post("/credits/recharge/record", null, { params: { amount, price } });
  return data;
}

export async function rechargePlaceholder(): Promise<{ ok: boolean; message: string }> {
  const { data } = await client.post("/credits/recharge");
  return data;
}
