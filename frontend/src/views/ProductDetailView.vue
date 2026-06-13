<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import { ElMessage } from "element-plus";
import { ArrowLeft, Plus, Refresh } from "@element-plus/icons-vue";
import client from "@/api/client";
import { useAuthStore } from "@/stores/auth";
import {
  getProduct,
  createTarget,
  regenerateTarget,
  type Product,
  type Target,
} from "@/api/products";

const auth = useAuthStore();
const route = useRoute();
const router = useRouter();

const productId = computed(() => route.params.id as string);
const product = ref<Product | null>(null);
const loading = ref(false);
const refBlobs = ref<Map<string, string>>(new Map());
const targetBlobs = ref<Map<string, string>>(new Map());

const showCreateDialog = ref(false);
const dialogPrompt = ref("");
const dialogCreating = ref(false);
const editingTargetId = ref<string | null>(null);
const regenPrompt = ref("");
const regenerating = ref(false);

let pollTimer: ReturnType<typeof setInterval> | null = null;

onMounted(async () => {
  await auth.loadProfile().catch(() => {});
  await loadProduct();
  startPolling();
});

onBeforeUnmount(() => {
  stopPolling();
  revokeBlobs();
});

function revokeBlobs() {
  refBlobs.value.forEach((url) => URL.revokeObjectURL(url));
  targetBlobs.value.forEach((url) => URL.revokeObjectURL(url));
}

watch(
  () => route.params.id,
  () => {
    revokeBlobs();
    refBlobs.value = new Map();
    targetBlobs.value = new Map();
    stopPolling();
    loadProduct();
    startPolling();
  },
);

async function loadProduct() {
  loading.value = true;
  try {
    product.value = await getProduct(productId.value);
    loadRefImages();
  } finally {
    loading.value = false;
  }
}

async function loadRefImages() {
  if (!product.value) return;
  for (const ref of product.value.ref_images) {
    if (refBlobs.value.has(ref.path)) continue;
    try {
      const resp = await client.get(`/products/${productId.value}/files/${ref.path}`, {
        responseType: "blob",
      });
      refBlobs.value.set(ref.path, URL.createObjectURL(resp.data));
    } catch {
      // ignore
    }
  }
}

async function loadTargetImage(target: Target) {
  if (!target.image_url || targetBlobs.value.has(target.id)) return;
  try {
    const cleanUrl = target.image_url.replace(/^\/api/, "");
    const resp = await client.get(cleanUrl, { responseType: "blob" });
    targetBlobs.value.set(target.id, URL.createObjectURL(resp.data));
  } catch {
    // ignore
  }
}

watch(
  () => product.value?.targets,
  (targets) => {
    if (!targets) return;
    targets.filter((t) => t.status === "success").forEach(loadTargetImage);
  },
  { deep: true, immediate: true },
);

function openCreateDialog() {
  dialogPrompt.value = "";
  showCreateDialog.value = true;
}

async function confirmCreate() {
  if (!dialogPrompt.value.trim()) {
    ElMessage.warning("请输入推广图提示词");
    return;
  }
  dialogCreating.value = true;
  try {
    await createTarget(productId.value, dialogPrompt.value.trim());
    ElMessage.success("产品推广图已加入生成队列");
    showCreateDialog.value = false;
    dialogPrompt.value = "";
    await loadProduct();
  } finally {
    dialogCreating.value = false;
  }
}

async function onSubmitRegen() {
  if (!editingTargetId.value || !regenPrompt.value.trim()) return;
  regenerating.value = true;
  try {
    await regenerateTarget(editingTargetId.value, regenPrompt.value.trim());
    ElMessage.success("已提交重新生成");
    editingTargetId.value = null;
    regenPrompt.value = "";
    await loadProduct();
  } finally {
    regenerating.value = false;
  }
}

function startPolling() {
  if (pollTimer) return;
  pollTimer = setInterval(async () => {
    if (!product.value) return;
    const hasActive = product.value.targets.some(
      (t) => t.status === "queued" || t.status === "generating",
    );
    if (hasActive) {
      const updated = await getProduct(productId.value).catch(() => null);
      if (updated) {
        product.value = updated;
        loadRefImages();
        updated.targets.filter((t) => t.status === "success").forEach(loadTargetImage);
      }
    }
  }, 3000);
}

function stopPolling() {
  if (pollTimer) {
    clearInterval(pollTimer);
    pollTimer = null;
  }
}

const PROGRESS_MAX = 95;

function targetProgress(target: Target): number {
  if (target.status === "success") return 100;
  if (target.status === "queued") return 0;
  if (target.status === "generating" && target.started_at) {
    const started = new Date(target.started_at).getTime();
    const elapsed = (Date.now() - started) / 1000;
    const pct = Math.min(elapsed / 120 * PROGRESS_MAX, PROGRESS_MAX);
    return Math.floor(pct);
  }
  return 0;
}

function startEditing(target: Target) {
  editingTargetId.value = target.id;
  regenPrompt.value = target.prompt;
}

function cancelEditing() {
  editingTargetId.value = null;
  regenPrompt.value = "";
}

const statusLabel: Record<string, string> = {
  queued: "排队中",
  generating: "生成中",
  success: "完成",
  failed: "失败",
};
const statusType: Record<string, string> = {
  queued: "info",
  generating: "warning",
  success: "success",
  failed: "danger",
};
</script>

<template>
  <div class="page">
    <el-main class="main">
      <div class="back-bar">
        <el-button text :icon="ArrowLeft" @click="router.push('/products')">返回产品列表</el-button>
      </div>

      <template v-if="product">
        <h2>{{ product.name }}</h2>

        <!-- 参考图 -->
        <el-card class="section">
          <template #header>参考图 ({{ product.ref_images.length }} 张)</template>
          <div class="ref-grid">
            <div v-for="ref in product.ref_images" :key="ref.path" class="ref-item">
              <img v-if="refBlobs.get(ref.path)" :src="refBlobs.get(ref.path)" alt="参考图" />
              <el-skeleton v-else animated :throttle="0" style="width:160px;height:160px" />
              <div class="ref-name">{{ ref.filename }}</div>
            </div>
          </div>
        </el-card>

        <!-- 产品推广图 -->
        <el-card class="section">
          <template #header>产品推广图 ({{ product.targets.length }})</template>
          <div v-if="product.targets.length === 0" class="empty-target-area" @click="openCreateDialog">
            <el-icon :size="40"><Plus /></el-icon>
            <span>点击创建产品推广图</span>
          </div>
          <div v-else class="target-grid">
            <el-card v-for="t in product.targets" :key="t.id" class="target-card" shadow="hover">
              <div class="target-img">
                <img v-if="t.status === 'success' && targetBlobs.get(t.id)" :src="targetBlobs.get(t.id)" alt="生成结果" />
                <div v-else-if="t.status === 'generating'" class="target-loading">
                  <el-progress :percentage="targetProgress(t)" :stroke-width="6" />
                  <span class="progress-text">生成中...</span>
                </div>
                <div v-else-if="t.status === 'queued'" class="target-placeholder queued">
                  <span>排队等待中</span>
                </div>
                <div v-else-if="t.status === 'failed'" class="target-placeholder failed">
                  <span>生成失败</span>
                  <span class="err-msg">{{ t.error_msg }}</span>
                </div>
                <el-skeleton v-else animated style="width:100%;height:200px" />
              </div>

              <div class="target-meta">
                <el-tag :type="statusType[t.status] || 'info'" size="small">{{ statusLabel[t.status] || t.status }}</el-tag>
                <span class="target-cost">消耗 {{ t.cost }} 积分</span>
              </div>

              <div class="target-prompt">{{ t.prompt }}</div>

              <div
                v-if="t.status === 'success' || t.status === 'failed'"
                class="target-actions"
              >
                <template v-if="editingTargetId === t.id">
                  <el-input
                    v-model="regenPrompt"
                    type="textarea"
                    :rows="2"
                    maxlength="1000"
                    show-word-limit
                    size="small"
                    class="regen-input"
                  />
                  <div class="regen-btns">
                    <el-button size="small" @click="cancelEditing">取消</el-button>
                    <el-button size="small" type="primary" :loading="regenerating" @click="onSubmitRegen">提交生成</el-button>
                  </div>
                </template>
                <template v-else>
                  <el-button
                    size="small"
                    text
                    type="primary"
                    :icon="Refresh"
                    @click="startEditing(t)"
                  >
                    调整提示词重新生成
                  </el-button>
                </template>
              </div>
            </el-card>

            <div class="add-target-card" @click="openCreateDialog">
              <el-icon :size="32"><Plus /></el-icon>
            </div>
          </div>
        </el-card>

        <el-dialog v-model="showCreateDialog" title="新建产品推广图" width="500px">
          <el-input
            v-model="dialogPrompt"
            type="textarea"
            :rows="4"
            maxlength="1000"
            show-word-limit
            placeholder="输入生成提示词，例如：更换背景为海滩日落"
          />
          <div class="dialog-cost">每次生成消耗 1 积分，当前剩余 {{ auth.credits }}</div>
          <template #footer>
            <el-button @click="showCreateDialog = false">取消</el-button>
            <el-button
              type="primary"
              :loading="dialogCreating"
              :disabled="!dialogPrompt.trim() || auth.credits <= 0"
              @click="confirmCreate"
            >
              确认生成
            </el-button>
          </template>
        </el-dialog>
      </template>
      <div v-else v-loading="loading" style="min-height:300px" />
    </el-main>
  </div>
</template>

<style scoped>
.page {
  min-height: 100vh;
  background: #f5f7fa;
}
.main {
  max-width: 1024px;
  margin: 0 auto;
}
.back-bar {
  margin-bottom: 8px;
}
.section {
  margin-bottom: 20px;
}
.ref-grid {
  display: flex;
  gap: 12px;
  flex-wrap: wrap;
}
.ref-item {
  text-align: center;
}
.ref-item img {
  width: 160px;
  height: 160px;
  object-fit: cover;
  border-radius: 6px;
  border: 1px solid #ebeef5;
}
.ref-name {
  font-size: 12px;
  color: #909399;
  margin-top: 4px;
  max-width: 160px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.target-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: 16px;
}

.empty-target-area {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 12px;
  padding: 60px 20px;
  border: 2px dashed #dcdfe6;
  border-radius: 8px;
  cursor: pointer;
  color: #c0c4cc;
  transition: border-color 0.2s, color 0.2s;
}
.empty-target-area:hover {
  border-color: #409eff;
  color: #409eff;
}
.empty-target-area span {
  font-size: 14px;
}

.add-target-card {
  display: flex;
  align-items: center;
  justify-content: center;
  aspect-ratio: 1;
  border: 2px dashed #dcdfe6;
  border-radius: 8px;
  cursor: pointer;
  color: #c0c4cc;
  transition: border-color 0.2s, color 0.2s;
}
.add-target-card:hover {
  border-color: #409eff;
  color: #409eff;
}

.dialog-cost {
  margin-top: 12px;
  font-size: 13px;
  color: #909399;
}
.target-card {
  display: flex;
  flex-direction: column;
}
.target-img {
  width: 100%;
  aspect-ratio: 1;
  background: #f5f7fa;
  border-radius: 6px;
  overflow: hidden;
  display: flex;
  align-items: center;
  justify-content: center;
}
.target-img img {
  width: 100%;
  height: 100%;
  object-fit: contain;
}
.target-loading {
  text-align: center;
  padding: 20px;
  width: 100%;
}
.progress-text {
  display: block;
  margin-top: 8px;
  font-size: 13px;
  color: #909399;
}
.target-placeholder {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
  color: #909399;
  font-size: 14px;
}
.target-placeholder.queued {
  color: #909399;
}
.target-placeholder.failed {
  color: #f56c6c;
}
.err-msg {
  font-size: 12px;
  max-width: 200px;
  text-align: center;
  word-break: break-all;
}
.target-meta {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-top: 10px;
}
.target-cost {
  font-size: 12px;
  color: #c0c4cc;
}
.target-prompt {
  margin-top: 8px;
  font-size: 13px;
  color: #606266;
  line-height: 1.5;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
.target-actions {
  margin-top: 10px;
  text-align: right;
}
.regen-input {
  margin-bottom: 6px;
}
.regen-btns {
  display: flex;
  gap: 8px;
  justify-content: flex-end;
}
</style>
