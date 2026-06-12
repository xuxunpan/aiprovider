import { defineStore } from "pinia";
import { fetchMe, login as apiLogin, register as apiRegister } from "@/api/auth";

interface AuthState {
  token: string | null;
  email: string | null;
  credits: number;
}

export const useAuthStore = defineStore("auth", {
  state: (): AuthState => ({
    token: localStorage.getItem("token"),
    email: null,
    credits: 0,
  }),
  getters: {
    isAuthenticated: (state) => !!state.token,
  },
  actions: {
    setToken(token: string) {
      this.token = token;
      localStorage.setItem("token", token);
    },
    async login(email: string, password: string) {
      const res = await apiLogin(email, password);
      this.setToken(res.access_token);
      await this.loadProfile();
    },
    async register(email: string, password: string) {
      const res = await apiRegister(email, password);
      this.setToken(res.access_token);
      await this.loadProfile();
    },
    async loadProfile() {
      const me = await fetchMe();
      this.email = me.email;
      this.credits = me.credits;
    },
    setCredits(credits: number) {
      this.credits = credits;
    },
    logout() {
      this.token = null;
      this.email = null;
      this.credits = 0;
      localStorage.removeItem("token");
    },
  },
});
