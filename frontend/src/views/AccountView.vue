<script setup lang="ts">
import { onMounted, reactive, ref } from "vue";
import { useRouter } from "vue-router";
import { ElMessage } from "element-plus";
import type { FormInstance, FormRules } from "element-plus";
import { useAuthStore } from "@/stores/auth";
import { getRechargeRecords, type RechargeRecord } from "@/api/credits";
import { changePassword } from "@/api/auth";

const auth = useAuthStore();
const router = useRouter();

const records = ref<RechargeRecord[]>([]);
const loadingRecords = ref(false);

const pwdFormRef = ref<FormInstance>();
const changingPwd = ref(false);
const pwdForm = reactive({ old_password: "", new_password: "", confirm: "" });

const pwdRules: FormRules = {
  old_password: [{ required: true, message: "请输入原密码", trigger: "blur" }],
  new_password: [
    { required: true, message: "请输入新密码", trigger: "blur" },
    { min: 6, max: 128, message: "密码长度至少 6 位", trigger: "blur" },
  ],
  confirm: [
    { required: true, message: "请再次输入新密码", trigger: "blur" },
    {
      validator: (_rule, value, callback) => {
        if (value !== pwdForm.new_password) callback(new Error("两次输入的密码不一致"));
        else callback();
      },
      trigger: "blur",
    },
  ],
};

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

async function onChangePwd() {
  if (!pwdFormRef.value) return;
  await pwdFormRef.value.validate(async (valid) => {
    if (!valid) return;
    changingPwd.value = true;
    try {
      await changePassword(pwdForm.old_password, pwdForm.new_password);
      ElMessage.success("密码修改成功");
      pwdFormRef.value?.resetFields();
    } catch {
      // 错误提示已在拦截器统一处理
    } finally {
      changingPwd.value = false;
    }
  });
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
          <el-descriptions-item label="账号角色">
            <el-tag :type="auth.isAdmin ? 'danger' : 'info'" size="small">
              {{ auth.isAdmin ? "管理员" : "普通用户" }}
            </el-tag>
          </el-descriptions-item>
        </el-descriptions>
        <div class="actions">
          <el-button type="primary" @click="router.push('/recharge')">充值入口</el-button>
          <el-button v-if="auth.isAdmin" @click="router.push('/admin/users')">用户管理</el-button>
        </div>
      </el-card>

      <el-card class="section">
        <template #header>修改密码</template>
        <el-form
          ref="pwdFormRef"
          :model="pwdForm"
          :rules="pwdRules"
          label-width="90px"
          @submit.prevent
        >
          <el-form-item label="原密码" prop="old_password">
            <el-input
              v-model="pwdForm.old_password"
              type="password"
              show-password
              placeholder="请输入原密码"
            />
          </el-form-item>
          <el-form-item label="新密码" prop="new_password">
            <el-input
              v-model="pwdForm.new_password"
              type="password"
              show-password
              placeholder="至少 6 位"
            />
          </el-form-item>
          <el-form-item label="确认密码" prop="confirm">
            <el-input
              v-model="pwdForm.confirm"
              type="password"
              show-password
              placeholder="请再次输入新密码"
            />
          </el-form-item>
          <el-form-item>
            <el-button type="primary" :loading="changingPwd" @click="onChangePwd">
              确认修改
            </el-button>
          </el-form-item>
        </el-form>
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
