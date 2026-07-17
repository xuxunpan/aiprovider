import { createRouter, createWebHashHistory } from "vue-router";
import { useAuthStore } from "@/stores/auth";

const router = createRouter({
  history: createWebHashHistory(),
  routes: [
    {
      path: "/login",
      name: "login",
      component: () => import("@/views/LoginView.vue"),
      meta: { public: true },
    },
    {
      path: "/register",
      name: "register",
      component: () => import("@/views/RegisterView.vue"),
      meta: { public: true },
    },
    {
      path: "/chat",
      name: "chat",
      component: () => import("@/views/ChatView.vue"),
    },
    {
      path: "/account",
      name: "account",
      component: () => import("@/views/AccountView.vue"),
    },
    {
      path: "/recharge",
      name: "recharge",
      component: () => import("@/views/RechargeView.vue"),
    },
    {
      path: "/admin/users",
      name: "adminUsers",
      component: () => import("@/views/AdminUsersView.vue"),
      meta: { requiresAdmin: true },
    },
    // 旧「我的产品」入口已下线，重定向到聊天页（视图文件保留不动）
    { path: "/products", redirect: "/chat" },
    { path: "/products/:id", redirect: "/chat" },
    { path: "/", redirect: "/chat" },
    { path: "/:pathMatch(.*)*", redirect: "/chat" },
  ],
});

router.beforeEach(async (to) => {
  const auth = useAuthStore();
  if (!to.meta.public && !auth.isAuthenticated) {
    return { name: "login" };
  }
  if (to.meta.public && auth.isAuthenticated) {
    return { name: "chat" };
  }
  // 管理员路由：需要加载资料后校验身份
  if (to.meta.requiresAdmin) {
    if (!auth.email) {
      try {
        await auth.loadProfile();
      } catch {
        return { name: "login" };
      }
    }
    if (!auth.isAdmin) {
      return { name: "chat" };
    }
  }
  return true;
});

export default router;
