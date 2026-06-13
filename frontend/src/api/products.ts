import client from "./client";

export interface RefImage {
  path: string;
  filename: string;
}

export interface Target {
  id: string;
  prompt: string;
  status: string;
  cost: number;
  image_url: string | null;
  error_msg: string | null;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
}

export interface Product {
  id: string;
  name: string;
  ref_images: RefImage[];
  targets: Target[];
  created_at: string;
  updated_at: string;
}

export interface ProductListItem {
  id: string;
  name: string;
  ref_count: number;
  target_count: number;
  target_status_summary: Record<string, number>;
  created_at: string;
  updated_at: string;
}

export interface ProductList {
  products: ProductListItem[];
}

export async function createProduct(name: string, images: File[]): Promise<{ product_id: string }> {
  const form = new FormData();
  form.append("name", name);
  images.forEach((img) => form.append("images", img));
  const { data } = await client.post("/products", form);
  return data;
}

export async function listProducts(): Promise<ProductList> {
  const { data } = await client.get<ProductList>("/products");
  return data;
}

export async function getProduct(id: string): Promise<Product> {
  const { data } = await client.get<Product>(`/products/${id}`);
  return data;
}

export async function deleteProduct(id: string): Promise<void> {
  await client.delete(`/products/${id}`);
}

export async function createTarget(productId: string, prompt: string): Promise<{ target_id: string; status: string }> {
  const { data } = await client.post(`/products/${productId}/targets`, { prompt });
  return data;
}

export async function regenerateTarget(targetId: string, prompt: string): Promise<{ target_id: string; status: string }> {
  const { data } = await client.post(`/targets/${targetId}/regenerate`, { prompt });
  return data;
}

export async function getTarget(targetId: string): Promise<Target> {
  const { data } = await client.get<Target>(`/targets/${targetId}`);
  return data;
}
