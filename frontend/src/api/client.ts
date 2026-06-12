import axios, { AxiosError } from "axios";
import { ElMessage } from "element-plus";
import router from "@/router";
import { useAuthStore } from "@/stores/auth";

const client = axios.create({
  baseURL: "/api",
  timeout: 180000,
});

client.interceptors.request.use((config) => {
  const auth = useAuthStore();
  if (auth.token) {
    config.headers.Authorization = `Bearer ${auth.token}`;
  }
  return config;
});

client.interceptors.response.use(
  (resp) => resp,
  (error: AxiosError<{ detail?: string }>) => {
    const status = error.response?.status;
    const detail = error.response?.data?.detail;

    if (status === 401) {
      const auth = useAuthStore();
      auth.logout();
      ElMessage.warning(detail || "登录已失效，请重新登录");
      router.push("/login");
    } else if (status === 402) {
      ElMessage.warning(detail || "积分已用完，请充值后继续使用");
      router.push("/recharge");
    } else if (detail) {
      ElMessage.error(detail);
    } else {
      ElMessage.error("网络异常，请稍后重试");
    }
    return Promise.reject(error);
  }
);

export default client;
