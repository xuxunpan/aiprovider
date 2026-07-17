import client from "./client";

export interface TokenResponse {
  access_token: string;
  token_type: string;
}

export interface UserResponse {
  id: string;
  email: string;
  credits: number;
  is_admin: boolean;
}

export async function register(email: string, password: string): Promise<TokenResponse> {
  const { data } = await client.post<TokenResponse>("/auth/register", { email, password });
  return data;
}

export async function login(email: string, password: string): Promise<TokenResponse> {
  const { data } = await client.post<TokenResponse>("/auth/login", { email, password });
  return data;
}

export async function fetchMe(): Promise<UserResponse> {
  const { data } = await client.get<UserResponse>("/auth/me");
  return data;
}

export async function checkRegistrationStatus(): Promise<{ enabled: boolean }> {
  const { data } = await client.get<{ enabled: boolean }>("/auth/registration-status");
  return data;
}

export async function changePassword(oldPassword: string, newPassword: string): Promise<void> {
  await client.post("/auth/change-password", {
    old_password: oldPassword,
    new_password: newPassword,
  });
}

// --- 管理员后台: 用户管理 ---

export interface AdminUser {
  id: string;
  email: string;
  credits: number;
  status: string;
  is_admin: boolean;
  created_at: string | null;
}

export async function adminListUsers(): Promise<AdminUser[]> {
  const { data } = await client.get<{ users: AdminUser[] }>("/auth/admin/users");
  return data.users;
}

export async function adminCreateUser(
  email: string,
  password: string,
  credits: number
): Promise<AdminUser> {
  const { data } = await client.post<AdminUser>("/auth/admin/users", { email, password, credits });
  return data;
}

export async function adminDeleteUser(userId: string): Promise<void> {
  await client.delete(`/auth/admin/users/${userId}`);
}

export async function adminResetPassword(userId: string, newPassword: string): Promise<void> {
  await client.post(`/auth/admin/users/${userId}/reset-password`, { new_password: newPassword });
}

export async function adminUpdateCredits(userId: string, credits: number): Promise<AdminUser> {
  const { data } = await client.patch<AdminUser>(
    `/auth/admin/users/${userId}/credits`,
    { credits }
  );
  return data;
}
