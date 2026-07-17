<script setup lang="ts">
import { onMounted, reactive, ref } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import type { FormInstance, FormRules } from "element-plus";
import { useAuthStore } from "@/stores/auth";
import {
  adminCreateUser,
  adminDeleteUser,
  adminListUsers,
  adminResetPassword,
  adminUpdateCredits,
  type AdminUser,
} from "@/api/auth";

const auth = useAuthStore();

const users = ref<AdminUser[]>([]);
const loading = ref(false);

// --- 添加用户 ---
const createVisible = ref(false);
const createFormRef = ref<FormInstance>();
const creating = ref(false);
const createForm = reactive({ email: "", password: "", credits: 20 });
const createRules: FormRules = {
  email: [
    { required: true, message: "请输入邮箱", trigger: "blur" },
    { type: "email", message: "邮箱格式不正确", trigger: "blur" },
  ],
  password: [
    { required: true, message: "请输入密码", trigger: "blur" },
    { min: 6, max: 128, message: "密码长度至少 6 位", trigger: "blur" },
  ],
  credits: [{ required: true, message: "请输入初始积分", trigger: "blur" }],
};

// --- 重置密码 ---
const resetVisible = ref(false);
const resetFormRef = ref<FormInstance>();
const resetting = ref(false);
const resetTarget = ref<AdminUser | null>(null);
const resetForm = reactive({ new_password: "" });
const resetRules: FormRules = {
  new_password: [
    { required: true, message: "请输入新密码", trigger: "blur" },
    { min: 6, max: 128, message: "密码长度至少 6 位", trigger: "blur" },
  ],
};

// --- 修改积分 ---
const creditsVisible = ref(false);
const creditsFormRef = ref<FormInstance>();
const updatingCredits = ref(false);
const creditsTarget = ref<AdminUser | null>(null);
const creditsForm = reactive({ credits: 0 });
const creditsRules: FormRules = {
  credits: [{ required: true, message: "请输入积分", trigger: "blur" }],
};

onMounted(async () => {
  await auth.loadProfile().catch(() => {});
  await loadUsers();
});

async function loadUsers() {
  loading.value = true;
  try {
    users.value = await adminListUsers();
  } finally {
    loading.value = false;
  }
}

function isSelf(row: AdminUser) {
  return auth.email != null && row.email.toLowerCase() === auth.email.toLowerCase();
}

function formatTime(ts: string | null) {
  if (!ts) return "-";
  return new Date(ts).toLocaleString("zh-CN");
}

// 添加用户
function openCreate() {
  createForm.email = "";
  createForm.password = "";
  createForm.credits = 20;
  createVisible.value = true;
}

async function onCreate() {
  if (!createFormRef.value) return;
  await createFormRef.value.validate(async (valid) => {
    if (!valid) return;
    creating.value = true;
    try {
      await adminCreateUser(createForm.email, createForm.password, Number(createForm.credits));
      ElMessage.success("用户添加成功");
      createVisible.value = false;
      await loadUsers();
    } catch {
      // 错误提示已在拦截器统一处理
    } finally {
      creating.value = false;
    }
  });
}

// 删除用户
async function onDelete(row: AdminUser) {
  try {
    await ElMessageBox.confirm(
      `确定要删除用户 ${row.email} 吗？该操作不可恢复。`,
      "删除确认",
      { type: "warning", confirmButtonText: "删除", cancelButtonText: "取消" }
    );
  } catch {
    return;
  }
  try {
    await adminDeleteUser(row.id);
    ElMessage.success("用户已删除");
    await loadUsers();
  } catch {
    // 错误提示已在拦截器统一处理
  }
}

// 重置密码
function openReset(row: AdminUser) {
  resetTarget.value = row;
  resetForm.new_password = "";
  resetVisible.value = true;
}

async function onReset() {
  if (!resetFormRef.value || !resetTarget.value) return;
  await resetFormRef.value.validate(async (valid) => {
    if (!valid) return;
    resetting.value = true;
    try {
      await adminResetPassword(resetTarget.value!.id, resetForm.new_password);
      ElMessage.success("密码已重置");
      resetVisible.value = false;
    } catch {
      // 错误提示已在拦截器统一处理
    } finally {
      resetting.value = false;
    }
  });
}

// 修改积分
function openCredits(row: AdminUser) {
  creditsTarget.value = row;
  creditsForm.credits = row.credits;
  creditsVisible.value = true;
}

async function onUpdateCredits() {
  if (!creditsFormRef.value || !creditsTarget.value) return;
  await creditsFormRef.value.validate(async (valid) => {
    if (!valid) return;
    updatingCredits.value = true;
    try {
      const updated = await adminUpdateCredits(
        creditsTarget.value!.id,
        Number(creditsForm.credits)
      );
      ElMessage.success("积分已更新");
      creditsVisible.value = false;
      // 本地同步
      const idx = users.value.findIndex((u) => u.id === updated.id);
      if (idx >= 0) users.value[idx] = updated;
      if (isSelf(updated)) auth.setCredits(updated.credits);
    } catch {
      // 错误提示已在拦截器统一处理
    } finally {
      updatingCredits.value = false;
    }
  });
}
</script>

<template>
  <div class="page">
    <el-main class="main">
      <div class="header-bar">
        <h2>用户管理</h2>
        <el-button type="primary" @click="openCreate">添加用户</el-button>
      </div>

      <el-card>
        <el-table v-loading="loading" :data="users" stripe>
          <el-table-column label="邮箱" min-width="220">
            <template #default="{ row }">
              <span>{{ row.email }}</span>
              <el-tag v-if="row.is_admin" type="danger" size="small" style="margin-left: 8px">管理员</el-tag>
              <el-tag v-if="isSelf(row)" type="success" size="small" style="margin-left: 8px">我</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="积分" width="100">
            <template #default="{ row }">{{ row.credits }}</template>
          </el-table-column>
          <el-table-column label="状态" width="90">
            <template #default="{ row }">
              <el-tag :type="row.status === 'active' ? 'success' : 'info'" size="small">
                {{ row.status === "active" ? "正常" : row.status }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column label="注册时间" width="180">
            <template #default="{ row }">{{ formatTime(row.created_at) }}</template>
          </el-table-column>
          <el-table-column label="操作" width="280" fixed="right">
            <template #default="{ row }">
              <el-button size="small" @click="openCredits(row)">修改积分</el-button>
              <el-button size="small" @click="openReset(row)">重置密码</el-button>
              <el-button
                size="small"
                type="danger"
                :disabled="row.is_admin || isSelf(row)"
                @click="onDelete(row)"
              >
                删除
              </el-button>
            </template>
          </el-table-column>
        </el-table>
      </el-card>
    </el-main>

    <!-- 添加用户 -->
    <el-dialog v-model="createVisible" title="添加用户" width="420px">
      <el-form
        ref="createFormRef"
        :model="createForm"
        :rules="createRules"
        label-width="80px"
        @submit.prevent
      >
        <el-form-item label="邮箱" prop="email">
          <el-input v-model="createForm.email" placeholder="请输入邮箱" />
        </el-form-item>
        <el-form-item label="密码" prop="password">
          <el-input
            v-model="createForm.password"
            type="password"
            show-password
            placeholder="至少 6 位"
          />
        </el-form-item>
        <el-form-item label="初始积分" prop="credits">
          <el-input-number v-model="createForm.credits" :min="0" :step="1" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="createVisible = false">取消</el-button>
        <el-button type="primary" :loading="creating" @click="onCreate">添加</el-button>
      </template>
    </el-dialog>

    <!-- 重置密码 -->
    <el-dialog v-model="resetVisible" title="重置密码" width="420px">
      <p class="dialog-tip" v-if="resetTarget">为用户 <b>{{ resetTarget.email }}</b> 设置新密码</p>
      <el-form
        ref="resetFormRef"
        :model="resetForm"
        :rules="resetRules"
        label-width="80px"
        @submit.prevent
      >
        <el-form-item label="新密码" prop="new_password">
          <el-input
            v-model="resetForm.new_password"
            type="password"
            show-password
            placeholder="至少 6 位"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="resetVisible = false">取消</el-button>
        <el-button type="primary" :loading="resetting" @click="onReset">确认重置</el-button>
      </template>
    </el-dialog>

    <!-- 修改积分 -->
    <el-dialog v-model="creditsVisible" title="修改积分" width="420px">
      <p class="dialog-tip" v-if="creditsTarget">设置用户 <b>{{ creditsTarget.email }}</b> 的积分余额</p>
      <el-form
        ref="creditsFormRef"
        :model="creditsForm"
        :rules="creditsRules"
        label-width="80px"
        @submit.prevent
      >
        <el-form-item label="积分" prop="credits">
          <el-input-number v-model="creditsForm.credits" :min="0" :step="1" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="creditsVisible = false">取消</el-button>
        <el-button type="primary" :loading="updatingCredits" @click="onUpdateCredits">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.page {
  min-height: 100vh;
  background: #f5f7fa;
}
.main {
  max-width: 1000px;
  margin: 0 auto;
}
.header-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 16px;
}
.header-bar h2 {
  margin: 0;
}
.dialog-tip {
  margin: 0 0 12px;
  color: #606266;
  font-size: 14px;
}
</style>
