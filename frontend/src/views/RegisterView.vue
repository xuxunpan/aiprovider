<script setup lang="ts">
import { reactive, ref, onMounted } from "vue";
import { useRouter } from "vue-router";
import { ElMessage } from "element-plus";
import type { FormInstance, FormRules } from "element-plus";
import { useAuthStore } from "@/stores/auth";
import { checkRegistrationStatus } from "@/api/auth";

const router = useRouter();
const auth = useAuthStore();
const formRef = ref<FormInstance>();
const loading = ref(false);
const registrationEnabled = ref(true);
const form = reactive({ email: "", password: "", confirm: "" });

onMounted(async () => {
  try {
    const { enabled } = await checkRegistrationStatus();
    registrationEnabled.value = enabled;
  } catch {
    registrationEnabled.value = true;
  }
});

const rules: FormRules = {
  email: [
    { required: true, message: "请输入邮箱", trigger: "blur" },
    { type: "email", message: "邮箱格式不正确", trigger: "blur" },
  ],
  password: [
    { required: true, message: "请输入密码", trigger: "blur" },
    { min: 6, message: "密码至少 6 位", trigger: "blur" },
  ],
  confirm: [
    {
      validator: (_r, value, cb) =>
        value === form.password ? cb() : cb(new Error("两次输入的密码不一致")),
      trigger: "blur",
    },
  ],
};

async function onSubmit() {
  if (!formRef.value) return;
  await formRef.value.validate(async (valid) => {
    if (!valid) return;
    loading.value = true;
    try {
      await auth.register(form.email, form.password);
      ElMessage.success("注册成功");
      router.push("/");
    } catch {
      // 错误提示已在拦截器统一处理
    } finally {
      loading.value = false;
    }
  });
}
</script>

<template>
  <div class="auth-wrap">
    <el-card class="auth-card">
      <template v-if="registrationEnabled">
        <h2 class="title">注册</h2>
        <el-form ref="formRef" :model="form" :rules="rules" label-position="top" @submit.prevent>
          <el-form-item label="邮箱" prop="email">
            <el-input v-model="form.email" placeholder="请输入邮箱" />
          </el-form-item>
          <el-form-item label="密码" prop="password">
            <el-input v-model="form.password" type="password" show-password placeholder="请输入密码" />
          </el-form-item>
          <el-form-item label="确认密码" prop="confirm">
            <el-input v-model="form.confirm" type="password" show-password placeholder="请再次输入密码" />
          </el-form-item>
          <el-button type="primary" :loading="loading" class="submit" @click="onSubmit">
            注册
          </el-button>
        </el-form>
        <div class="foot">
          已有账号？<router-link to="/login">返回登录</router-link>
        </div>
      </template>
      <template v-else>
        <h2 class="title">注册已关闭</h2>
        <p class="closed-msg">当前暂不开放新用户注册，如有疑问请联系管理员。</p>
        <div class="foot">
          <router-link to="/login">返回登录</router-link>
        </div>
      </template>
    </el-card>
  </div>
</template>

<style scoped>
.auth-wrap {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  background: #f5f7fa;
}
.auth-card {
  width: 380px;
}
.title {
  text-align: center;
  margin: 0 0 16px;
}
.submit {
  width: 100%;
}
.foot {
  margin-top: 16px;
  text-align: center;
  font-size: 14px;
}
.closed-msg {
  text-align: center;
  color: #909399;
  margin: 16px 0;
}
</style>
