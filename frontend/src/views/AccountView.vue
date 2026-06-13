<script setup lang="ts">
import { onMounted, ref } from "vue";
import { useRouter } from "vue-router";
import { useAuthStore } from "@/stores/auth";
import { getRechargeRecords, type RechargeRecord } from "@/api/credits";

const auth = useAuthStore();
const router = useRouter();

const records = ref<RechargeRecord[]>([]);
const loadingRecords = ref(false);

onMounted(async () => {
  await auth.loadProfile().catch(() => {});
  loadRecords();
});

async function loadRecords() {
  loadingRecords.value = true;
  try {
    const res = await getRechargeRecords();
    records.value = res.records;
  } finally {
    loadingRecords.value = false;
  }
}

function formatTime(ts: string) {
  return new Date(ts).toLocaleString("zh-CN");
}

const statusLabel: Record<string, string> = {
  pending: "待处理",
  completed: "已完成",
  failed: "已失败",
};
</script>

<template>
  <div class="page">
    <el-main class="main">
      <h2>我的账户</h2>

      <el-card class="section">
        <el-descriptions :column="1" border>
          <el-descriptions-item label="邮箱">{{ auth.email }}</el-descriptions-item>
          <el-descriptions-item label="当前积分">
            <el-tag type="warning" effect="dark" round>{{ auth.credits }} 积分</el-tag>
          </el-descriptions-item>
        </el-descriptions>
        <div class="actions">
          <el-button type="primary" @click="router.push('/recharge')">充值入口</el-button>
        </div>
      </el-card>

      <el-card class="section">
        <template #header>充值记录</template>
        <el-table v-loading="loadingRecords" :data="records" stripe empty-text="暂无充值记录">
          <el-table-column label="金额" width="120">
            <template #default="{ row }">¥{{ row.price }}</template>
          </el-table-column>
          <el-table-column label="积分" width="120">
            <template #default="{ row }">{{ row.amount_credits }} 积分</template>
          </el-table-column>
          <el-table-column label="状态" width="120">
            <template #default="{ row }">
              <el-tag :type="row.status === 'pending' ? 'info' : 'success'" size="small">
                {{ statusLabel[row.status] || row.status }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column label="时间">
            <template #default="{ row }">{{ formatTime(row.created_at) }}</template>
          </el-table-column>
        </el-table>
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
.section {
  margin-bottom: 20px;
}
.actions {
  margin-top: 16px;
  text-align: center;
}
</style>
