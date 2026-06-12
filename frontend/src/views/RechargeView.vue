<script setup lang="ts">
import { ref } from "vue";
import { ElMessage } from "element-plus";
import AppHeader from "@/components/AppHeader.vue";
import { recharge } from "@/api/images";

const loading = ref(false);

async function onRecharge() {
  loading.value = true;
  try {
    const res = await recharge();
    ElMessage.info(res.message);
  } catch {
    // 拦截器已处理
  } finally {
    loading.value = false;
  }
}
</script>

<template>
  <el-container class="page">
    <AppHeader />
    <el-main>
      <el-card class="card">
        <h2>积分充值</h2>
        <el-alert
          title="充值功能即将上线"
          type="info"
          :closable="false"
          description="目前充值功能正在建设中，敬请期待。如急需更多积分，请联系平台客服。"
          show-icon
        />
        <div class="plans">
          <el-card v-for="p in [
            { credits: 50, price: 9 },
            { credits: 120, price: 19 },
            { credits: 300, price: 39 },
          ]" :key="p.credits" class="plan" shadow="hover">
            <div class="credits">{{ p.credits }} 积分</div>
            <div class="price">¥{{ p.price }}</div>
            <el-button type="primary" :loading="loading" @click="onRecharge">立即充值</el-button>
          </el-card>
        </div>
      </el-card>
    </el-main>
  </el-container>
</template>

<style scoped>
.page {
  min-height: 100vh;
  background: #f5f7fa;
}
.card {
  max-width: 760px;
  margin: 0 auto;
}
.plans {
  display: flex;
  gap: 16px;
  margin-top: 24px;
}
.plan {
  flex: 1;
  text-align: center;
}
.credits {
  font-size: 20px;
  font-weight: 600;
}
.price {
  font-size: 24px;
  color: #f56c6c;
  margin: 12px 0;
}
</style>
