<script setup lang="ts">
import { computed, onMounted } from "vue";
import { useRoute, useRouter } from "vue-router";
import { ElMessage } from "element-plus";
import { useAuthStore } from "@/stores/auth";

const auth = useAuthStore();
const router = useRouter();
const route = useRoute();

const activeTab = computed(() => {
  if (route.path.startsWith("/account") || route.path.startsWith("/recharge")) return "account";
  return "products";
});

onMounted(() => {
  if (auth.isAuthenticated && !auth.email) {
    auth.loadProfile().catch(() => {});
  }
});

function onLogout() {
  auth.logout();
  ElMessage.success("已退出登录");
  router.push("/login");
}
</script>

<template>
  <el-header class="app-header" height="56px">
    <div class="header-left">
      <span class="brand">AI生成电商产品推广图</span>
      <div class="tabs">
        <span
          class="tab"
          :class="{ active: activeTab === 'products' }"
          @click="router.push('/products')"
        >我的商品</span>
        <span
          class="tab"
          :class="{ active: activeTab === 'account' }"
          @click="router.push('/account')"
        >我</span>
      </div>
    </div>
    <div class="header-right">
      <el-tag type="warning" effect="dark" round>积分：{{ auth.credits }}</el-tag>
      <span class="email" @click="router.push('/account')">{{ auth.email }}</span>
      <el-button text type="danger" @click="onLogout">退出</el-button>
    </div>
  </el-header>
</template>

<style scoped>
.app-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  background: #fff;
  border-bottom: 1px solid #e4e7ed;
  padding: 0 24px;
  box-shadow: 0 1px 4px rgba(0, 0, 0, 0.04);
}
.header-left {
  display: flex;
  align-items: center;
  gap: 32px;
}
.brand {
  font-size: 17px;
  font-weight: 700;
  color: #303133;
  letter-spacing: 0.5px;
}
.tabs {
  display: flex;
  gap: 4px;
}
.tab {
  padding: 6px 16px;
  font-size: 14px;
  color: #606266;
  cursor: pointer;
  border-radius: 6px;
  transition: all 0.2s;
}
.tab:hover {
  color: #409eff;
  background: #ecf5ff;
}
.tab.active {
  color: #409eff;
  background: #ecf5ff;
  font-weight: 600;
}
.header-right {
  display: flex;
  align-items: center;
  gap: 16px;
}
.email {
  font-size: 13px;
  color: #409eff;
  cursor: pointer;
  transition: opacity 0.2s;
}
.email:hover {
  opacity: 0.8;
}
</style>
