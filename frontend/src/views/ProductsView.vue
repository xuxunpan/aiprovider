<script setup lang="ts">
import { onMounted, ref } from "vue";
import { useRouter } from "vue-router";
import { ElMessage, ElMessageBox } from "element-plus";
import { Plus } from "@element-plus/icons-vue";
import { useAuthStore } from "@/stores/auth";
import { listProducts, deleteProduct, createProduct, type ProductListItem } from "@/api/products";

const auth = useAuthStore();
const router = useRouter();

const products = ref<ProductListItem[]>([]);
const loading = ref(false);
const showCreate = ref(false);
const createName = ref("");
const createLoading = ref(false);
const createFiles = ref<File[]>([]);

const ALLOWED = ["image/png", "image/jpeg", "image/webp"];
const MAX_MB = 10;

const statusLabels: Record<string, string> = {
  queued: "排队中",
  generating: "生成中",
  success: "已完成",
  failed: "已失败",
};
const statusColors: Record<string, string> = {
  queued: "info",
  generating: "warning",
  success: "success",
  failed: "danger",
};

onMounted(() => {
  auth.loadProfile().catch(() => {});
  loadProducts();
});

async function loadProducts() {
  loading.value = true;
  try {
    const res = await listProducts();
    products.value = res.products;
  } finally {
    loading.value = false;
  }
}

function handleFileChange(file: File) {
  if (!ALLOWED.includes(file.type)) {
    ElMessage.error("仅支持 PNG、JPG、WEBP 格式的图片");
    return;
  }
  if (file.size > MAX_MB * 1024 * 1024) {
    ElMessage.error(`图片大小不能超过 ${MAX_MB}MB`);
    return;
  }
  createFiles.value.push(file);
}

function removeFile(index: number) {
  createFiles.value.splice(index, 1);
}

async function onCreate() {
  if (!createName.value.trim()) {
    ElMessage.warning("请输入产品名称");
    return;
  }
  if (createFiles.value.length === 0) {
    ElMessage.warning("请至少上传一张参考图");
    return;
  }
  createLoading.value = true;
  try {
    const res = await createProduct(createName.value.trim(), createFiles.value);
    ElMessage.success("产品创建成功");
    showCreate.value = false;
    createName.value = "";
    createFiles.value = [];
    router.push(`/products/${res.product_id}`);
  } finally {
    createLoading.value = false;
  }
}

async function onDelete(product: ProductListItem) {
  try {
    await ElMessageBox.confirm(`确定删除产品「${product.name}」？所有目标图也将被删除。`, "确认删除", {
      type: "warning",
      confirmButtonText: "删除",
      cancelButtonText: "取消",
    });
  } catch {
    return;
  }
  try {
    await deleteProduct(product.id);
    ElMessage.success("产品已删除");
    products.value = products.value.filter((p) => p.id !== product.id);
  } catch {
    // 拦截器已处理
  }
}
</script>

<template>
  <div class="page">
    <el-main class="main">
      <div class="toolbar">
        <h2>产品列表</h2>
        <el-button type="primary" :icon="Plus" @click="showCreate = true">新建产品</el-button>
      </div>

      <div v-loading="loading" class="list">
        <el-empty v-if="!loading && products.length === 0" description="暂无产品，点击上方按钮新建" />
        <el-card
          v-for="p in products"
          :key="p.id"
          class="product-card"
          shadow="hover"
          @click="router.push(`/products/${p.id}`)"
        >
          <div class="card-header">
            <span class="name">{{ p.name }}</span>
            <span class="meta">参考图 {{ p.ref_count }} 张 · 目标图 {{ p.target_count }} 个</span>
          </div>
          <div class="card-status">
            <template v-if="p.target_count === 0">
              <el-tag type="info" size="small">暂无目标图</el-tag>
            </template>
            <template v-else>
              <el-tag
                v-for="(count, status) in p.target_status_summary"
                :key="status"
                :type="statusColors[status] || 'info'"
                size="small"
              >
                {{ statusLabels[status] || status }} {{ count }}
              </el-tag>
            </template>
          </div>
          <div class="card-actions" @click.stop>
            <el-button text type="danger" size="small" @click="onDelete(p)">删除</el-button>
          </div>
        </el-card>
      </div>
    </el-main>

    <!-- 新建产品对话框 -->
    <el-dialog v-model="showCreate" title="新建产品" width="560px">
      <el-form label-position="top">
        <el-form-item label="产品名称" required>
          <el-input v-model="createName" placeholder="例如：春季新品海报" maxlength="60" show-word-limit />
        </el-form-item>
        <el-form-item label="上传参考图（可多张）" required>
          <div class="upload-area">
            <el-upload
              :show-file-list="false"
              :auto-upload="false"
              :on-change="(file: any) => handleFileChange(file.raw)"
              accept="image/png,image/jpeg,image/webp"
              multiple
              drag
            >
              <el-icon :size="32"><Plus /></el-icon>
              <div>点击或拖拽上传参考图</div>
              <div class="hint">支持 PNG / JPG / WEBP，最大 {{ MAX_MB }}MB</div>
            </el-upload>
          </div>
          <div v-if="createFiles.length > 0" class="file-list">
            <el-tag
              v-for="(f, i) in createFiles"
              :key="i"
              closable
              @close="removeFile(i)"
              size="small"
            >
              {{ f.name }}
            </el-tag>
          </div>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showCreate = false">取消</el-button>
        <el-button type="primary" :loading="createLoading" @click="onCreate">创建</el-button>
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
  max-width: 960px;
  margin: 0 auto;
}
.toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 20px;
}
.toolbar h2 {
  margin: 0;
  font-size: 20px;
}
.list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.product-card {
  cursor: pointer;
}
.product-card .card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8px;
}
.product-card .name {
  font-size: 16px;
  font-weight: 600;
}
.product-card .meta {
  font-size: 13px;
  color: #909399;
}
.card-status {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
  margin-bottom: 4px;
}
.card-actions {
  text-align: right;
  margin-top: 4px;
}
.upload-area {
  width: 100%;
}
.upload-area :deep(.el-upload-dragger) {
  height: 140px;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
}
.hint {
  font-size: 12px;
  color: #c0c4cc;
  margin-top: 4px;
}
.file-list {
  margin-top: 12px;
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
}
</style>
