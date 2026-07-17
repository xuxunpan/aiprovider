<script setup lang="ts">
import { nextTick, onBeforeUnmount, onMounted, ref, computed } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import { Plus, Delete, UploadFilled } from "@element-plus/icons-vue";
import MarkdownIt from "markdown-it";
import { useAuthStore } from "@/stores/auth";
import {
  listSessions,
  createSession,
  getSession,
  deleteSession,
  sendMessageStream,
  type ChatSessionListItem,
  type ChatMessage,
} from "@/api/chat";

const auth = useAuthStore();

const md = new MarkdownIt({ html: false, breaks: true, linkify: true });

interface UIMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  images: { path: string; filename: string }[];
  previewUrls: string[];
  status: string;
  error_msg: string | null;
  streaming?: boolean;
}

const sessions = ref<ChatSessionListItem[]>([]);
const currentId = ref<string | null>(null);
const messages = ref<UIMessage[]>([]);
const inputText = ref("");
const inputFiles = ref<File[]>([]);
const sending = ref(false);
const loadingSession = ref(false);
const sessionsLoading = ref(false);

const ALLOWED = ["image/png", "image/jpeg", "image/webp"];
const MAX_MB = 10;
const MAX_IMAGES = 4;

const messagesEl = ref<HTMLElement | null>(null);
const fileInputEl = ref<HTMLInputElement | null>(null);

const hasInput = computed(() => inputText.value.trim() || inputFiles.value.length > 0);

onMounted(() => {
  auth.loadProfile().catch(() => {});
  loadSessions();
});

onBeforeUnmount(() => {
  // 组件卸载即放弃流式（fetch 已发出则后端自行结束）
});

async function loadSessions() {
  sessionsLoading.value = true;
  try {
    const res = await listSessions();
    sessions.value = res.sessions;
    if (sessions.value.length > 0 && !currentId.value) {
      await selectSession(sessions.value[0].id);
    }
  } finally {
    sessionsLoading.value = false;
  }
}

async function selectSession(id: string) {
  if (sending.value) return;
  currentId.value = id;
  messages.value = [];
  loadingSession.value = true;
  try {
    const detail = await getSession(id);
    messages.value = detail.messages.map(toUIMessage);
    await nextTick();
    scrollToBottom();
  } finally {
    loadingSession.value = false;
  }
}

function toUIMessage(m: ChatMessage): UIMessage {
  return {
    id: m.id,
    role: m.role,
    content: m.content,
    images: m.images,
    previewUrls: [],
    status: m.status,
    error_msg: m.error_msg,
  };
}

async function onNewSession() {
  if (sending.value) return;
  try {
    const res = await createSession();
    const item: ChatSessionListItem = {
      id: res.session_id,
      title: "新会话",
      last_message_at: null,
      created_at: new Date().toISOString(),
    };
    sessions.value.unshift(item);
    await selectSession(item.id);
  } catch {
    /* 拦截器已处理 */
  }
}

async function onDeleteSession(id: string) {
  try {
    await ElMessageBox.confirm("确定删除该会话？所有聊天记录将被清除。", "确认删除", {
      type: "warning",
      confirmButtonText: "删除",
      cancelButtonText: "取消",
    });
  } catch {
    return;
  }
  try {
    await deleteSession(id);
    sessions.value = sessions.value.filter((s) => s.id !== id);
    if (currentId.value === id) {
      currentId.value = null;
      messages.value = [];
      if (sessions.value.length > 0) {
        await selectSession(sessions.value[0].id);
      }
    }
    ElMessage.success("会话已删除");
  } catch {
    /* 拦截器已处理 */
  }
}

function onFilePick() {
  fileInputEl.value?.click();
}

function onFileChange(e: Event) {
  const target = e.target as HTMLInputElement;
  if (!target.files) return;
  for (const file of Array.from(target.files)) {
    if (inputFiles.value.length >= MAX_IMAGES) {
      ElMessage.warning(`最多上传 ${MAX_IMAGES} 张图片`);
      break;
    }
    if (!ALLOWED.includes(file.type)) {
      ElMessage.error("仅支持 PNG、JPG、WEBP 格式的图片");
      continue;
    }
    if (file.size > MAX_MB * 1024 * 1024) {
      ElMessage.error(`图片大小不能超过 ${MAX_MB}MB`);
      continue;
    }
    inputFiles.value.push(file);
  }
  target.value = "";
}

function removeFile(index: number) {
  inputFiles.value.splice(index, 1);
}

function fileUrl(file: File): string {
  return URL.createObjectURL(file);
}

function imageUrl(path: string): string {
  if (!currentId.value) return "";
  const filename = path.split("/").pop() || "";
  return `/api/chat/sessions/${currentId.value}/files/${filename}`;
}

async function onSend() {
  if (sending.value) return;
  if (!hasInput.value) return;
  if (!currentId.value) {
    ElMessage.warning("请先选择或新建会话");
    return;
  }

  const text = inputText.value.trim();
  const files = [...inputFiles.value];
  const sid = currentId.value;

  // 立即插入用户消息 + 占位助手消息
  const userMsg: UIMessage = {
    id: `local-u-${Date.now()}`,
    role: "user",
    content: text,
    images: files.map((f) => ({ path: f.name, filename: f.name })),
    previewUrls: files.map((f) => URL.createObjectURL(f)),
    status: "success",
    error_msg: null,
  };
  const assistantMsg: UIMessage = {
    id: `local-a-${Date.now()}`,
    role: "assistant",
    content: "",
    images: [],
    previewUrls: [],
    status: "streaming",
    error_msg: null,
    streaming: true,
  };
  messages.value.push(userMsg, assistantMsg);
  inputText.value = "";
  inputFiles.value = [];
  sending.value = true;
  await nextTick();
  scrollToBottom();

  let doneText = "";
  try {
    await sendMessageStream(sid, text, files, {
      onDelta: (delta) => {
        assistantMsg.content += delta;
        scrollToBottom();
      },
      onDone: (finalText, _usage) => {
        doneText = finalText;
        assistantMsg.content = finalText || assistantMsg.content;
        assistantMsg.streaming = false;
        assistantMsg.status = "success";
      },
      onError: (detail) => {
        assistantMsg.streaming = false;
        assistantMsg.status = "failed";
        assistantMsg.error_msg = detail;
        if (!assistantMsg.content) {
          assistantMsg.content = `❌ ${detail}`;
        }
      },
    });
  } finally {
    sending.value = false;
    // 刷新积分与会话列表（标题/排序可能变化）
    auth.loadProfile().catch(() => {});
    refreshSessionMeta(sid, doneText || assistantMsg.content);
  }
}

function refreshSessionMeta(sid: string, lastContent: string) {
  const idx = sessions.value.findIndex((s) => s.id === sid);
  if (idx === -1) return;
  const s = sessions.value[idx];
  s.last_message_at = new Date().toISOString();
  if (s.title === "新会话" && lastContent) {
    s.title = lastContent.replace(/\n/g, " ").slice(0, 24);
  }
  // 移到顶部
  sessions.value.splice(idx, 1);
  sessions.value.unshift(s);
}

function onTextareaKeydown(e: KeyboardEvent) {
  if (e.key === "Enter" && !e.shiftKey) {
    e.preventDefault();
    onSend();
  }
}

function scrollToBottom() {
  nextTick(() => {
    const el = messagesEl.value;
    if (el) el.scrollTop = el.scrollHeight;
  });
}

function renderMarkdown(content: string): string {
  return md.render(content || "");
}
</script>

<template>
  <div class="chat-page">
    <el-container class="chat-container">
      <!-- 左侧会话列表 -->
      <el-aside class="sidebar" width="280px">
        <div class="sidebar-header">
          <span class="sidebar-title">我的会话</span>
          <el-button type="primary" size="small" :icon="Plus" @click="onNewSession">新建</el-button>
        </div>
        <div v-loading="sessionsLoading" class="session-list">
          <el-empty
            v-if="!sessionsLoading && sessions.length === 0"
            description="暂无会话"
            :image-size="60"
          />
          <div
            v-for="s in sessions"
            :key="s.id"
            class="session-item"
            :class="{ active: s.id === currentId }"
            @click="selectSession(s.id)"
          >
            <div class="session-name">{{ s.title }}</div>
            <el-button
              class="session-del"
              text
              size="small"
              type="danger"
              :icon="Delete"
              @click.stop="onDeleteSession(s.id)"
            />
          </div>
        </div>
      </el-aside>

      <!-- 中间会话区 -->
      <el-main class="chat-main">
        <div v-if="!currentId" class="empty-chat">
          <el-empty description="选择左侧会话或点击「新建」开始对话" />
        </div>
        <template v-else>
          <!-- 消息流 -->
          <div ref="messagesEl" class="messages" v-loading="loadingSession">
            <div
              v-for="msg in messages"
              :key="msg.id"
              class="msg-row"
              :class="msg.role"
            >
              <div class="msg-avatar">{{ msg.role === "user" ? "我" : "AI" }}</div>
              <div class="msg-bubble-wrap">
                <div v-if="msg.images.length > 0 || msg.previewUrls.length > 0" class="msg-images">
                  <template v-if="msg.previewUrls.length > 0">
                    <img
                      v-for="(url, i) in msg.previewUrls"
                      :key="i"
                      :src="url"
                      class="msg-img"
                      alt=""
                    />
                  </template>
                  <template v-else>
                    <img
                      v-for="(img, i) in msg.images"
                      :key="i"
                      :src="imageUrl(img.path)"
                      class="msg-img"
                      alt=""
                    />
                  </template>
                </div>
                <div class="msg-bubble" :class="{ failed: msg.status === 'failed' }">
                  <div
                    v-if="msg.role === 'assistant'"
                    class="msg-content markdown-body"
                    v-html="renderMarkdown(msg.content)"
                  />
                  <div v-else class="msg-content">{{ msg.content }}</div>
                  <span v-if="msg.streaming" class="cursor">▋</span>
                </div>
                <div v-if="msg.error_msg && msg.status === 'failed'" class="msg-error">
                  {{ msg.error_msg }}
                </div>
              </div>
            </div>
          </div>

          <!-- 输入区 -->
          <div class="input-area">
            <div v-if="inputFiles.length > 0" class="input-previews">
              <div v-for="(f, i) in inputFiles" :key="i" class="preview-item">
                <img :src="fileUrl(f)" class="preview-img" alt="" />
                <span class="preview-remove" @click="removeFile(i)">×</span>
              </div>
            </div>
            <div class="input-row">
              <el-button
                class="upload-btn"
                circle
                :icon="UploadFilled"
                :disabled="sending || inputFiles.length >= MAX_IMAGES"
                @click="onFilePick"
              />
              <input
                ref="fileInputEl"
                type="file"
                accept="image/png,image/jpeg,image/webp"
                multiple
                hidden
                @change="onFileChange"
              />
              <el-input
                v-model="inputText"
                type="textarea"
                :autosize="{ minRows: 1, maxRows: 6 }"
                placeholder="输入消息，Enter 发送，Shift+Enter 换行"
                resize="none"
                :disabled="sending"
                @keydown="onTextareaKeydown"
              />
              <el-button
                type="primary"
                :loading="sending"
                :disabled="!hasInput"
                @click="onSend"
              >发送</el-button>
            </div>
            <div class="input-hint">
              可同时发送最多 {{ MAX_IMAGES }} 张图片（PNG/JPG/WEBP，≤{{ MAX_MB }}MB）· 每条消息消耗积分
            </div>
          </div>
        </template>
      </el-main>
    </el-container>
  </div>
</template>

<style scoped>
.chat-page {
  height: calc(100vh - 56px);
  background: #f5f7fa;
}
.chat-container {
  height: 100%;
}
.sidebar {
  background: #fff;
  border-right: 1px solid #e4e7ed;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}
.sidebar-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 14px 16px;
  border-bottom: 1px solid #f0f0f0;
}
.sidebar-title {
  font-size: 15px;
  font-weight: 700;
  color: #303133;
}
.session-list {
  flex: 1;
  overflow-y: auto;
  padding: 8px;
}
.session-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 12px;
  border-radius: 8px;
  cursor: pointer;
  transition: background 0.15s;
  margin-bottom: 4px;
}
.session-item:hover {
  background: #f5f7fa;
}
.session-item.active {
  background: #ecf5ff;
}
.session-item.active .session-name {
  color: #409eff;
  font-weight: 600;
}
.session-name {
  font-size: 14px;
  color: #606266;
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.session-del {
  opacity: 0;
  flex-shrink: 0;
}
.session-item:hover .session-del {
  opacity: 1;
}

.chat-main {
  display: flex;
  flex-direction: column;
  padding: 0;
  overflow: hidden;
}
.empty-chat {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
}
.messages {
  flex: 1;
  overflow-y: auto;
  padding: 24px;
}
.msg-row {
  display: flex;
  gap: 12px;
  margin-bottom: 24px;
  max-width: 900px;
  margin-left: auto;
  margin-right: auto;
}
.msg-row.user {
  flex-direction: row-reverse;
}
.msg-avatar {
  width: 36px;
  height: 36px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 13px;
  font-weight: 600;
  flex-shrink: 0;
  background: #409eff;
  color: #fff;
}
.msg-row.user .msg-avatar {
  background: #67c23a;
}
.msg-bubble-wrap {
  display: flex;
  flex-direction: column;
  min-width: 0;
}
.msg-row.user .msg-bubble-wrap {
  align-items: flex-end;
}
.msg-images {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
  margin-bottom: 6px;
}
.msg-img {
  width: 120px;
  height: 120px;
  object-fit: cover;
  border-radius: 8px;
  border: 1px solid #e4e7ed;
}
.msg-bubble {
  padding: 10px 14px;
  border-radius: 10px;
  font-size: 14px;
  line-height: 1.6;
  word-break: break-word;
  max-width: 680px;
  background: #fff;
  border: 1px solid #e4e7ed;
}
.msg-row.assistant .msg-bubble {
  border-top-left-radius: 2px;
}
.msg-row.user .msg-bubble {
  background: #ecf5ff;
  border-color: #d9ecff;
  border-top-right-radius: 2px;
}
.msg-bubble.failed {
  background: #fef0f0;
  border-color: #fbc4c4;
  color: #f56c6c;
}
.msg-content {
  white-space: pre-wrap;
}
.msg-row.assistant .msg-content {
  white-space: normal;
}
.cursor {
  display: inline-block;
  color: #409eff;
  animation: blink 1s steps(2) infinite;
}
@keyframes blink {
  50% {
    opacity: 0;
  }
}
.msg-error {
  font-size: 12px;
  color: #f56c6c;
  margin-top: 4px;
  max-width: 680px;
}

.input-area {
  border-top: 1px solid #e4e7ed;
  background: #fff;
  padding: 12px 24px 16px;
}
.input-previews {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  margin-bottom: 8px;
}
.preview-item {
  position: relative;
}
.preview-img {
  width: 64px;
  height: 64px;
  object-fit: cover;
  border-radius: 6px;
  border: 1px solid #e4e7ed;
}
.preview-remove {
  position: absolute;
  top: -6px;
  right: -6px;
  width: 18px;
  height: 18px;
  border-radius: 50%;
  background: #f56c6c;
  color: #fff;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 12px;
  cursor: pointer;
  line-height: 1;
}
.input-row {
  display: flex;
  align-items: flex-end;
  gap: 8px;
  max-width: 900px;
  margin: 0 auto;
}
.upload-btn {
  flex-shrink: 0;
}
.input-hint {
  font-size: 12px;
  color: #c0c4cc;
  margin-top: 6px;
  text-align: center;
  max-width: 900px;
  margin-left: auto;
  margin-right: auto;
}

.markdown-body :deep(pre) {
  background: #f6f8fa;
  border-radius: 6px;
  padding: 12px;
  overflow-x: auto;
  margin: 8px 0;
}
.markdown-body :deep(code) {
  font-family: Consolas, Monaco, monospace;
  font-size: 13px;
}
.markdown-body :deep(p) {
  margin: 6px 0;
}
.markdown-body :deep(ul),
.markdown-body :deep(ol) {
  padding-left: 20px;
  margin: 6px 0;
}
</style>
