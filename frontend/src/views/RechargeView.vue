<script setup lang="ts">
import { ref, onMounted, onUnmounted } from "vue";
import { ElMessage } from "element-plus";
import QRCode from "qrcode";
import { createRecharge, getRechargeStatus, getRechargePackages, type RechargePackage } from "@/api/credits";
import { useAuthStore } from "@/stores/auth";

const auth = useAuthStore();
const loadingPlan = ref<string | null>(null);
const plans = ref<RechargePackage[]>([]);

const dialogVisible = ref(false);
const qrDataUrl = ref("");
const currentRecordId = ref("");
const currentCredits = ref(0);
const currentPrice = ref(0);
const expireCountdown = ref(0);
let pollTimer: ReturnType<typeof setInterval> | null = null;
let countdownTimer: ReturnType<typeof setInterval> | null = null;

const QR_EXPIRE_SECONDS = 7200;

onMounted(async () => {
  try {
    const res = await getRechargePackages();
    plans.value = res.packages;
  } catch {
    ElMessage.error("加载充值套餐失败");
  }
});

onUnmounted(() => {
  clearAllTimers();
});

function clearAllTimers() {
  if (pollTimer !== null) {
    clearInterval(pollTimer);
    pollTimer = null;
  }
  if (countdownTimer !== null) {
    clearInterval(countdownTimer);
    countdownTimer = null;
  }
}

async function onRecharge(plan: RechargePackage) {
  loadingPlan.value = plan.id;
  try {
    const res = await createRecharge(plan.id);
    if (res.code_url) {
      currentRecordId.value = res.record_id;
      currentCredits.value = plan.credits;
      currentPrice.value = plan.price;
      qrDataUrl.value = await QRCode.toDataURL(res.code_url, { width: 260, margin: 1 });
      expireCountdown.value = QR_EXPIRE_SECONDS;
      dialogVisible.value = true;
      startPolling();
      startCountdown(plan);
    } else {
      ElMessage.info(res.message || "充值功能即将上线，敬请期待。");
    }
  } catch {
    // 错误已在拦截器中处理
  } finally {
    loadingPlan.value = null;
  }
}

function startCountdown(pkg: RechargePackage) {
  countdownTimer = setInterval(() => {
    expireCountdown.value--;
    if (expireCountdown.value <= 0) {
      onRefreshQr(pkg);
    }
  }, 1000);
}

async function onRefreshQr(pkg?: RechargePackage) {
  clearAllTimers();
  if (!pkg) {
    const found = plans.value.find((p) => p.price === currentPrice.value);
    if (!found) return;
    pkg = found;
  }
  try {
    const res = await createRecharge(pkg.id);
    if (res.code_url) {
      currentRecordId.value = res.record_id;
      qrDataUrl.value = await QRCode.toDataURL(res.code_url, { width: 260, margin: 1 });
      expireCountdown.value = QR_EXPIRE_SECONDS;
      startPolling();
      startCountdown(pkg);
    } else {
      ElMessage.error("刷新二维码失败");
      dialogVisible.value = false;
    }
  } catch {
    ElMessage.error("刷新二维码失败");
    dialogVisible.value = false;
  }
}

function startPolling() {
  pollTimer = setInterval(async () => {
    try {
      const status = await getRechargeStatus(currentRecordId.value);
      if (status.status === "completed") {
        clearAllTimers();
        auth.setCredits(auth.credits + status.amount_credits);
        ElMessage.success(`充值成功！获得 ${status.amount_credits} 积分`);
        dialogVisible.value = false;
      }
    } catch {
      // 轮询失败忽略，继续下次
    }
  }, 5000);
}

function onDialogClose() {
  clearAllTimers();
}

function formatCountdown(seconds: number): string {
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  const s = seconds % 60;
  return `${h.toString().padStart(2, "0")}:${m.toString().padStart(2, "0")}:${s.toString().padStart(2, "0")}`;
}
</script>

<template>
  <div class="page">
    <el-main class="main">
      <el-card>
        <h2>积分充值</h2>
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

    <el-dialog
      v-model="dialogVisible"
      title="微信扫码支付"
      width="380px"
      :close-on-click-modal="false"
      @close="onDialogClose"
    >
      <div class="qr-wrapper">
        <img v-if="qrDataUrl" :src="qrDataUrl" alt="支付二维码" class="qr-img" />
        <div class="qr-info">
          <p class="qr-amount">充值 {{ currentCredits }} 积分 / &yen;{{ currentPrice }}</p>
          <p class="qr-tip">请使用微信「扫一扫」扫码支付</p>
          <p class="qr-countdown" :class="{ warning: expireCountdown < 300 }">
            二维码有效期: {{ formatCountdown(expireCountdown) }}
          </p>
        </div>
        <div class="qr-actions">
          <el-button text type="primary" @click="onRefreshQr()">刷新二维码</el-button>
        </div>
      </div>
    </el-dialog>
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

.qr-wrapper {
  text-align: center;
  padding: 16px 0;
}
.qr-img {
  width: 260px;
  height: 260px;
  border: 1px solid #ebeef5;
  border-radius: 4px;
}
.qr-info {
  margin-top: 16px;
}
.qr-amount {
  font-size: 16px;
  font-weight: 600;
  margin: 0 0 8px;
}
.qr-tip {
  font-size: 13px;
  color: #909399;
  margin: 0 0 4px;
}
.qr-countdown {
  font-size: 13px;
  color: #606266;
  margin: 0;
}
.qr-countdown.warning {
  color: #f56c6c;
}
.qr-actions {
  margin-top: 16px;
}
</style>
