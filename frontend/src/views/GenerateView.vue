<script setup lang="ts">
import { ref } from "vue";
import { ElMessage } from "element-plus";
import type { UploadRawFile, UploadRequestOptions } from "element-plus";
import { Plus } from "@element-plus/icons-vue";
import AppHeader from "@/components/AppHeader.vue";
import client from "@/api/client";
import { generateImage } from "@/api/images";
import { useAuthStore } from "@/stores/auth";

const auth = useAuthStore();

const prompt = ref("");
const selectedFile = ref<File | null>(null);
const previewUrl = ref<string>("");
const resultUrl = ref<string>("");
const loading = ref(false);

const ALLOWED = ["image/png", "image/jpeg", "image/webp"];
const MAX_MB = 10;

function beforeUpload(file: UploadRawFile): boolean {
  if (!ALLOWED.includes(file.type)) {
    ElMessage.error("仅支持 PNG、JPG、WEBP 格式的图片");
    return false;
  }
  if (file.size > MAX_MB * 1024 * 1024) {
    ElMessage.error(`图片大小不能超过 ${MAX_MB}MB`);
    return false;
  }
  return true;
}

// 阻止 el-upload 自动上传，仅本地保留文件
function handleRequest(options: UploadRequestOptions) {
  const file = options.file as File;
  selectedFile.value = file;
  if (previewUrl.value) URL.revokeObjectURL(previewUrl.value);
  previewUrl.value = URL.createObjectURL(file);
  return Promise.resolve();
}

async function onGenerate() {
  if (!selectedFile.value) {
    ElMessage.warning("请先上传一张参考图片");
    return;
  }
  if (!prompt.value.trim()) {
    ElMessage.warning("请输入图片说明文字");
    return;
  }
  if (auth.credits <= 0) {
    ElMessage.warning("积分已用完，请充值后继续使用");
    return;
  }

  loading.value = true;
  try {
    const res = await generateImage(prompt.value.trim(), selectedFile.value);
    auth.setCredits(res.credits);
    // 图片接口需要鉴权头，用 axios 拉 blob 再转 objectURL
    const imgResp = await client.get(res.image_url.replace(/^\/api/, ""), {
      responseType: "blob",
    });
    if (resultUrl.value) URL.revokeObjectURL(resultUrl.value);
    resultUrl.value = URL.createObjectURL(imgResp.data);
    ElMessage.success("图片生成成功");
  } catch {
    // 错误提示（含积分不足/退还）已在拦截器统一处理
  } finally {
    loading.value = false;
  }
}
</script>

<template>
  <el-container class="page">
    <AppHeader />
    <el-main>
      <el-row :gutter="20">
        <el-col :span="12">
          <el-card header="① 上传图片并输入说明">
            <el-upload
              class="uploader"
              drag
              :show-file-list="false"
              :before-upload="beforeUpload"
              :http-request="handleRequest"
              accept="image/png,image/jpeg,image/webp"
            >
              <img v-if="previewUrl" :src="previewUrl" class="preview" alt="预览" />
              <div v-else class="placeholder">
                <el-icon :size="40"><Plus /></el-icon>
                <div>点击或拖拽图片到此处</div>
                <div class="hint">支持 PNG / JPG / WEBP，最大 {{ MAX_MB }}MB</div>
              </div>
            </el-upload>

            <el-input
              v-model="prompt"
              type="textarea"
              :rows="4"
              maxlength="1000"
              show-word-limit
              placeholder="请输入对生成图片的说明文字，例如：把背景换成星空"
              class="prompt"
            />

            <el-button
              type="primary"
              size="large"
              class="gen-btn"
              :loading="loading"
              :disabled="auth.credits <= 0"
              @click="onGenerate"
            >
              生成图片（消耗积分）
            </el-button>
            <div v-if="auth.credits <= 0" class="no-credit">
              积分已用完，请先<router-link to="/recharge">充值</router-link>
            </div>
          </el-card>
        </el-col>

        <el-col :span="12">
          <el-card header="② 生成结果">
            <div v-loading="loading" class="result">
              <img v-if="resultUrl" :src="resultUrl" class="result-img" alt="生成结果" />
              <el-empty v-else description="生成结果将在这里显示" />
            </div>
          </el-card>
        </el-col>
      </el-row>
    </el-main>
  </el-container>
</template>

<style scoped>
.page {
  min-height: 100vh;
  background: #f5f7fa;
}
.uploader :deep(.el-upload-dragger) {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 260px;
}
.preview {
  max-width: 100%;
  max-height: 240px;
  object-fit: contain;
}
.placeholder {
  color: #909399;
  text-align: center;
}
.hint {
  font-size: 12px;
  margin-top: 6px;
}
.prompt {
  margin-top: 16px;
}
.gen-btn {
  margin-top: 16px;
  width: 100%;
}
.no-credit {
  margin-top: 10px;
  text-align: center;
  color: #e6a23c;
  font-size: 14px;
}
.result {
  min-height: 320px;
  display: flex;
  align-items: center;
  justify-content: center;
}
.result-img {
  max-width: 100%;
  max-height: 480px;
  object-fit: contain;
}
</style>
