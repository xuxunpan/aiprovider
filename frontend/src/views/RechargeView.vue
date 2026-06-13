<script setup lang="ts">
import { ref, onMounted } from "vue";
import { ElMessage } from "element-plus";
import { rechargePlaceholder, createRechargeRecord, getRechargePackages, type RechargePackage } from "@/api/credits";

const loadingPlan = ref<string | null>(null);
const plans = ref<RechargePackage[]>([]);

onMounted(async () => {
  try {
    const res = await getRechargePackages();
    plans.value = res.packages;
  } catch {
    ElMessage.error("加载充值套餐失败");
  }
});

async function onRecharge(plan: RechargePackage) {
  loadingPlan.value = plan.id;
  try {
    await createRechargeRecord(plan.id);
    const res = await rechargePlaceholder();
    ElMessage.info(res.message);
  } finally {
    loadingPlan.value = null;
  }
}
</script>

<template>
  <div class="page">
    <el-main class="main">
      <el-card>
        <h2>积分充值</h2>
        <el-alert
          title="充值功能即将上线"
          type="info"
          :closable="false"
          description="目前充值功能正在建设中，敬请期待。如急需更多积分，请联系平台客服。"
          show-icon
        />
        <div class="plans">
          <el-card v-for="p in plans" :key="p.id" class="plan" shadow="hover">
            <div class="credits">{{ p.credits }} 积分</div>
            <div class="price">&yen;{{ p.price }}</div>
            <el-button
              type="primary"
              :loading="loadingPlan === p.id"
              @click="onRecharge(p)"
            >
              立即充值
            </el-button>
          </el-card>
        </div>
      </el-card>
    </el-main>
  </div>
</template>

<style scoped>
.page {
  min-height: 100vh;
  background: #f5f7fa;
}
.main {
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
