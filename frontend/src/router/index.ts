import { createRouter, createWebHistory } from "vue-router";
import { useAuthStore } from "@/stores/auth";

const router = createRouter({
  history: createWebHistory(),
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
      path: "/products",
      name: "products",
      component: () => import("@/views/ProductsView.vue"),
    },
    {
      path: "/products/:id",
      name: "productDetail",
      component: () => import("@/views/ProductDetailView.vue"),
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
    { path: "/", redirect: "/products" },
    { path: "/:pathMatch(.*)*", redirect: "/products" },
  ],
});

router.beforeEach((to) => {
  const auth = useAuthStore();
  if (!to.meta.public && !auth.isAuthenticated) {
    return { name: "login" };
  }
  if (to.meta.public && auth.isAuthenticated) {
    return { name: "products" };
  }
  return true;
});

export default router;
