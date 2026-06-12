<script setup lang="ts">
import { onMounted } from "vue";
import { useRouter } from "vue-router";
import { ElMessage } from "element-plus";
import { useAuthStore } from "@/stores/auth";

const auth = useAuthStore();
const router = useRouter();

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
  <el-header class="app-header">
    <div class="brand" @click="router.push('/')">AI 图片生成平台</div>
    <div class="right">
      <el-tag type="warning" effect="dark" round>积分：{{ auth.credits }}</el-tag>
      <el-button text @click="router.push('/recharge')">充值</el-button>
      <span class="email">{{ auth.email }}</span>
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
  border-bottom: 1px solid #ebeef5;
}
.brand {
  font-size: 18px;
  font-weight: 600;
  cursor: pointer;
}
.right {
  display: flex;
  align-items: center;
  gap: 12px;
}
.email {
  font-size: 14px;
  color: #909399;
}
</style>
