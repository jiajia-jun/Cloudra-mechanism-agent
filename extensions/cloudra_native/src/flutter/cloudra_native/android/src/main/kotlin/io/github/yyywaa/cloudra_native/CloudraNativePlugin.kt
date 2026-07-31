package io.github.yyywaa.cloudra_native

import android.Manifest
import android.app.Activity
import android.app.NotificationManager
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.graphics.Bitmap
import android.net.Uri
import android.os.Build
import android.os.Handler
import android.os.Looper
import android.os.SystemClock
import android.provider.DocumentsContract
import android.provider.MediaStore
import android.provider.OpenableColumns
import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyProperties
import android.util.Base64
import io.flutter.embedding.engine.plugins.FlutterPlugin
import io.flutter.embedding.engine.plugins.activity.ActivityAware
import io.flutter.embedding.engine.plugins.activity.ActivityPluginBinding
import io.flutter.plugin.common.MethodCall
import io.flutter.plugin.common.MethodChannel
import io.flutter.plugin.common.PluginRegistry
import java.io.ByteArrayOutputStream
import java.nio.ByteBuffer
import java.security.KeyPairGenerator
import java.security.KeyStore
import java.security.MessageDigest
import java.security.interfaces.RSAPublicKey
import java.security.spec.MGF1ParameterSpec
import java.util.concurrent.ExecutorService
import java.util.concurrent.Executors
import javax.crypto.Cipher
import javax.crypto.KeyGenerator
import javax.crypto.Mac
import javax.crypto.SecretKey
import javax.crypto.spec.OAEPParameterSpec
import javax.crypto.spec.PSource
import javax.crypto.spec.SecretKeySpec
import javax.crypto.spec.GCMParameterSpec

class CloudraNativePlugin :
    FlutterPlugin,
    MethodChannel.MethodCallHandler,
    ActivityAware,
    PluginRegistry.ActivityResultListener,
    PluginRegistry.RequestPermissionsResultListener {

    companion object {
        private const val CHANNEL = "io.github.yyywaa.cloudra/native"
        private const val REQUEST_TREE = 71241
        private const val REQUEST_FILE = 71242
        private const val REQUEST_CAMERA = 71243
        private const val REQUEST_NOTIFICATIONS = 71244
        private const val LEGACY_TREE_PREF = "document_tree_uri"
        private const val TREE_RECORD = "cloudra.native.document_tree_uri"
        private const val MAX_TRANSFER_BYTES = 1_048_576
    }

    private lateinit var context: Context
    private lateinit var channel: MethodChannel
    private lateinit var secureStore: KeystoreStore
    private lateinit var secureTransport: SecureTransport
    private var activity: Activity? = null
    private var activityBinding: ActivityPluginBinding? = null
    private val executor: ExecutorService = Executors.newSingleThreadExecutor()
    private val mainHandler = Handler(Looper.getMainLooper())
    private var pendingActivity: PendingActivity? = null
    private var pendingPermission: MethodChannel.Result? = null

    private data class PendingActivity(
        val kind: String,
        val result: MethodChannel.Result,
        val maxBytes: Int = 262_144,
    )

    private data class DocumentInfo(
        val uri: Uri,
        val name: String,
        val mimeType: String,
        val size: Long?,
    )

    override fun onAttachedToEngine(binding: FlutterPlugin.FlutterPluginBinding) {
        context = binding.applicationContext
        secureStore = KeystoreStore(context)
        secureTransport = SecureTransport()
        channel = MethodChannel(binding.binaryMessenger, CHANNEL)
        channel.setMethodCallHandler(this)
        CloudraForegroundService.ensureChannels(context)
    }

    override fun onDetachedFromEngine(binding: FlutterPlugin.FlutterPluginBinding) {
        channel.setMethodCallHandler(null)
        secureTransport.clear()
        executor.shutdown()
    }

    override fun onAttachedToActivity(binding: ActivityPluginBinding) {
        activity = binding.activity
        activityBinding = binding
        binding.addActivityResultListener(this)
        binding.addRequestPermissionsResultListener(this)
    }

    override fun onDetachedFromActivityForConfigChanges() {
        detachActivity(cancelPending = false)
    }

    override fun onReattachedToActivityForConfigChanges(binding: ActivityPluginBinding) {
        onAttachedToActivity(binding)
    }

    override fun onDetachedFromActivity() {
        detachActivity(cancelPending = true)
    }

    private fun detachActivity(cancelPending: Boolean) {
        activityBinding?.removeActivityResultListener(this)
        activityBinding?.removeRequestPermissionsResultListener(this)
        activityBinding = null
        activity = null
        if (cancelPending) {
            pendingActivity?.result?.success(
                mapOf(
                    "status" to "cancelled",
                    "error" to "Android Activity 已关闭",
                )
            )
            pendingActivity = null
            pendingPermission?.success(
                mapOf(
                    "status" to "permission_denied",
                    "granted" to false,
                    "error" to "Android Activity 已关闭",
                )
            )
            pendingPermission = null
        }
    }

    override fun onMethodCall(call: MethodCall, result: MethodChannel.Result) {
        val arguments = call.arguments as? Map<*, *> ?: emptyMap<Any, Any>()
        when (call.method) {
            "ping" -> result.success(
                mapOf(
                    "status" to "ok",
                    "platform" to "android",
                    "sdk_int" to Build.VERSION.SDK_INT,
                )
            )
            "secure_transport_public_key" -> secureTransportPublicKey(result)
            "secure_transport_open" -> openSecureTransport(arguments, result)
            "secure_set_encrypted" -> secureSetEncrypted(arguments, result)
            "secure_get_encrypted" -> secureGetEncrypted(arguments, result)
            "secure_remove" -> secureRemove(arguments, result)
            "secure_contains" -> secureContains(arguments, result)
            "notification_permission_status" -> result.success(
                notificationPermission()
            )
            "request_notification_permission" -> requestNotificationPermission(result)
            "start_foreground_runtime" -> startForeground(arguments, result)
            "update_foreground_runtime" -> updateForeground(arguments, result)
            "stop_foreground_runtime" -> stopForeground(result)
            "show_notification" -> showNotification(arguments, result)
            "cancel_notification" -> cancelNotification(arguments, result)
            "select_document_tree" -> selectDocumentTree(result)
            "get_document_tree" -> runIo(result) { documentTreeStatus() }
            "revoke_document_tree" -> runIo(result) { revokeDocumentTree() }
            "documents_list" -> runIo(result) { listDocuments(arguments) }
            "documents_read" -> runIo(result) { readDocument(arguments) }
            "documents_write" -> runIo(result) { writeDocument(arguments) }
            "pick_file" -> pickFile(arguments, result)
            "capture_photo" -> capturePhoto(result)
            "share_text" -> shareText(arguments, result)
            else -> result.notImplemented()
        }
    }

    private fun key(arguments: Map<*, *>): String {
        val value = arguments["key"]?.toString()?.trim().orEmpty()
        require(value.matches(Regex("[A-Za-z0-9._:-]{1,200}"))) {
            "invalid secure-storage key"
        }
        return value
    }

    private fun secureTransportPublicKey(result: MethodChannel.Result) {
        try {
            result.success(secureTransport.publicKey())
        } catch (error: Exception) {
            result.success(failed(error))
        }
    }

    private fun openSecureTransport(
        arguments: Map<*, *>,
        result: MethodChannel.Result,
    ) {
        try {
            val wrapped = arguments["wrapped_key"] as? String
                ?: throw IllegalArgumentException("wrapped_key must be base64")
            val sessionId = secureTransport.openSession(wrapped)
            result.success(
                mapOf(
                    "status" to "ok",
                    "session_id" to sessionId,
                )
            )
        } catch (error: Exception) {
            result.success(failed(error))
        }
    }

    private fun secureSetEncrypted(
        arguments: Map<*, *>,
        result: MethodChannel.Result,
    ) {
        var plaintext: ByteArray? = null
        try {
            val storageKey = key(arguments)
            plaintext = secureTransport.openEnvelope(
                arguments,
                "set:$storageKey".toByteArray(Charsets.UTF_8),
            )
            require(plaintext.size <= MAX_TRANSFER_BYTES) {
                "secure-storage value is too large"
            }
            secureStore.set(storageKey, plaintext)
            result.success(mapOf("status" to "ok"))
        } catch (_: SecureTransport.SessionExpired) {
            result.success(
                mapOf("status" to "session_expired", "error" to "安全传输会话已过期")
            )
        } catch (error: Exception) {
            result.success(failed(error))
        } finally {
            plaintext?.fill(0)
        }
    }

    private fun secureGetEncrypted(
        arguments: Map<*, *>,
        result: MethodChannel.Result,
    ) {
        var plaintext: ByteArray? = null
        try {
            val storageKey = key(arguments)
            // Resolve the session even when the key is absent so callers cannot
            // keep using an expired transport indefinitely.
            secureTransport.requireSession(arguments)
            plaintext = secureStore.get(storageKey)
            if (plaintext == null) {
                result.success(mapOf("status" to "ok", "found" to false))
                return
            }
            val response = mutableMapOf<String, Any>(
                "status" to "ok",
                "found" to true,
            )
            response.putAll(
                secureTransport.sealEnvelope(
                    arguments,
                    plaintext,
                    "get:$storageKey".toByteArray(Charsets.UTF_8),
                )
            )
            result.success(response)
        } catch (_: SecureTransport.SessionExpired) {
            result.success(
                mapOf("status" to "session_expired", "error" to "安全传输会话已过期")
            )
        } catch (error: Exception) {
            result.success(failed(error))
        } finally {
            plaintext?.fill(0)
        }
    }

    private fun secureRemove(arguments: Map<*, *>, result: MethodChannel.Result) {
        try {
            result.success(
                mapOf(
                    "status" to "ok",
                    "removed" to secureStore.remove(key(arguments)),
                )
            )
        } catch (error: Exception) {
            result.success(failed(error))
        }
    }

    private fun secureContains(arguments: Map<*, *>, result: MethodChannel.Result) {
        try {
            result.success(
                mapOf(
                    "status" to "ok",
                    "contains" to secureStore.contains(key(arguments)),
                )
            )
        } catch (error: Exception) {
            result.success(failed(error))
        }
    }

    private fun notificationPermission(): Map<String, Any> {
        val granted = Build.VERSION.SDK_INT < Build.VERSION_CODES.TIRAMISU ||
            context.checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) ==
            PackageManager.PERMISSION_GRANTED
        return mapOf(
            "status" to if (granted) "granted" else "permission_denied",
            "granted" to granted,
        )
    }

    private fun requestNotificationPermission(result: MethodChannel.Result) {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.TIRAMISU) {
            result.success(notificationPermission())
            return
        }
        if (context.checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) ==
            PackageManager.PERMISSION_GRANTED
        ) {
            result.success(notificationPermission())
            return
        }
        val host = activity
        if (host == null) {
            result.success(
                mapOf(
                    "status" to "unavailable",
                    "error" to "Android Activity 当前不可用",
                )
            )
            return
        }
        if (pendingPermission != null || pendingActivity != null) {
            result.success(busy())
            return
        }
        pendingPermission = result
        host.requestPermissions(
            arrayOf(Manifest.permission.POST_NOTIFICATIONS),
            REQUEST_NOTIFICATIONS,
        )
    }

    override fun onRequestPermissionsResult(
        requestCode: Int,
        permissions: Array<out String>,
        grantResults: IntArray,
    ): Boolean {
        if (requestCode != REQUEST_NOTIFICATIONS) return false
        val result = pendingPermission ?: return true
        pendingPermission = null
        val granted = grantResults.isNotEmpty() &&
            grantResults[0] == PackageManager.PERMISSION_GRANTED
        val canAskAgain = activity?.shouldShowRequestPermissionRationale(
            Manifest.permission.POST_NOTIFICATIONS
        ) ?: false
        result.success(
            mapOf(
                "status" to if (granted) "granted" else "permission_denied",
                "granted" to granted,
                "can_ask_again" to canAskAgain,
            )
        )
        return true
    }

    private fun startForeground(
        arguments: Map<*, *>,
        result: MethodChannel.Result,
    ) {
        val title = arguments["title"]?.toString()?.trim()
            ?.takeIf { it.isNotEmpty() } ?: "Cloudra 设备 Runtime"
        val text = arguments["text"]?.toString()?.trim()
            ?.takeIf { it.isNotEmpty() } ?: "设备工具节点在线"
        val route = safeRoute(arguments["route"]?.toString())
        val intent = Intent(context, CloudraForegroundService::class.java).apply {
            action = CloudraForegroundService.ACTION_START
            putExtra(CloudraForegroundService.EXTRA_TITLE, title)
            putExtra(CloudraForegroundService.EXTRA_TEXT, text)
            putExtra(CloudraForegroundService.EXTRA_ROUTE, route)
        }
        try {
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                context.startForegroundService(intent)
            } else {
                context.startService(intent)
            }
            context.getSharedPreferences("cloudra_native_state", Context.MODE_PRIVATE)
                .edit().putBoolean("runtime_enabled", true).apply()
            val permission = notificationPermission().toMutableMap()
            permission["runtime_started"] = true
            result.success(permission)
        } catch (error: SecurityException) {
            result.success(permissionDenied(error))
        } catch (error: IllegalStateException) {
            result.success(
                mapOf(
                    "status" to "background_start_denied",
                    "error" to safeError(error),
                )
            )
        }
    }

    private fun stopForeground(result: MethodChannel.Result) {
        try {
            context.stopService(
                Intent(context, CloudraForegroundService::class.java)
            )
            val manager =
                context.getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
            manager.cancel(CloudraForegroundService.NOTIFICATION_ID)
            context.getSharedPreferences("cloudra_native_state", Context.MODE_PRIVATE)
                .edit().putBoolean("runtime_enabled", false).apply()
            result.success(mapOf("status" to "ok", "runtime_started" to false))
        } catch (error: Exception) {
            result.success(failed(error))
        }
    }

    private fun updateForeground(
        arguments: Map<*, *>,
        result: MethodChannel.Result,
    ) {
        val preferences =
            context.getSharedPreferences("cloudra_native_state", Context.MODE_PRIVATE)
        if (!preferences.getBoolean("runtime_enabled", false)) {
            result.success(
                mapOf(
                    "status" to "not_running",
                    "runtime_started" to false,
                    "error" to "前台服务尚未启动",
                )
            )
            return
        }
        val title = arguments["title"]?.toString()?.trim()
            ?.takeIf { it.isNotEmpty() } ?: "Cloudra 设备 Runtime"
        val text = arguments["text"]?.toString()?.trim()
            ?.takeIf { it.isNotEmpty() } ?: "设备工具节点在线"
        val route = safeRoute(arguments["route"]?.toString())
        preferences.edit()
            .putString(CloudraForegroundService.EXTRA_TITLE, title)
            .putString(CloudraForegroundService.EXTRA_TEXT, text)
            .putString(CloudraForegroundService.EXTRA_ROUTE, route)
            .apply()
        val manager =
            context.getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
        manager.notify(
            CloudraForegroundService.NOTIFICATION_ID,
            CloudraForegroundService.buildNotification(
                context,
                CloudraForegroundService.CHANNEL_ID,
                title,
                text,
                route,
                ongoing = true,
            ),
        )
        val permission = notificationPermission().toMutableMap()
        permission["runtime_started"] = true
        result.success(permission)
    }

    private fun showNotification(
        arguments: Map<*, *>,
        result: MethodChannel.Result,
    ) {
        if (notificationPermission()["granted"] != true) {
            result.success(
                mapOf(
                    "status" to "permission_denied",
                    "error" to "通知权限未授予",
                )
            )
            return
        }
        val title = arguments["title"]?.toString()?.trim().orEmpty()
        val text = arguments["text"]?.toString()?.trim().orEmpty()
        if (title.isEmpty() || text.isEmpty()) {
            result.success(
                mapOf("status" to "failed", "error" to "title/text 不能为空")
            )
            return
        }
        val route = safeRoute(arguments["route"]?.toString())
        val notificationId = notificationId(arguments, fallback = text)
        val manager =
            context.getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
        manager.notify(
            notificationId,
            CloudraForegroundService.buildNotification(
                context,
                CloudraForegroundService.APPROVAL_CHANNEL_ID,
                title,
                text,
                route,
                ongoing = false,
            ),
        )
        result.success(mapOf("status" to "ok"))
    }

    private fun cancelNotification(
        arguments: Map<*, *>,
        result: MethodChannel.Result,
    ) {
        try {
            val notificationId = notificationId(arguments)
            val manager =
                context.getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
            manager.cancel(notificationId)
            result.success(mapOf("status" to "ok", "cancelled" to true))
        } catch (error: Exception) {
            result.success(failed(error))
        }
    }

    private fun notificationId(
        arguments: Map<*, *>,
        fallback: String? = null,
    ): Int {
        val explicit = arguments["notification_id"]?.toString()?.trim()
            ?.takeIf { it.isNotEmpty() }
        if (explicit != null) {
            require(explicit.length <= 200) {
                "notification_id 长度不能超过 200"
            }
            return notificationNamespaceId(explicit)
        }
        val raw = fallback
            ?: throw IllegalArgumentException("notification_id 不能为空")
        return notificationNamespaceId(raw)
    }

    private fun notificationNamespaceId(value: String): Int =
        (value.hashCode() and 0x3fffffff) or 0x40000000

    private fun safeRoute(raw: String?): String {
        val route = raw?.trim().orEmpty()
        return if (route.startsWith("cloudra://") && route.length <= 500) {
            route
        } else {
            "cloudra://runtime/status"
        }
    }

    private fun selectDocumentTree(result: MethodChannel.Result) {
        val host = activity
        if (host == null) {
            result.success(unavailableActivity())
            return
        }
        if (pendingActivity != null || pendingPermission != null) {
            result.success(busy())
            return
        }
        pendingActivity = PendingActivity("tree", result)
        val intent = Intent(Intent.ACTION_OPEN_DOCUMENT_TREE).apply {
            addFlags(
                Intent.FLAG_GRANT_READ_URI_PERMISSION or
                    Intent.FLAG_GRANT_WRITE_URI_PERMISSION or
                    Intent.FLAG_GRANT_PERSISTABLE_URI_PERMISSION or
                    Intent.FLAG_GRANT_PREFIX_URI_PERMISSION
            )
        }
        try {
            host.startActivityForResult(intent, REQUEST_TREE)
        } catch (error: Exception) {
            pendingActivity = null
            result.success(failed(error))
        }
    }

    private fun documentTreeStatus(): Map<String, Any?> {
        val uri = authorizedTreeUri()
            ?: return mapOf(
                "status" to "not_authorized",
                "authorized" to false,
            )
        val root = rootDocument(uri)
        val writable = context.contentResolver.persistedUriPermissions.any {
            it.uri == uri && it.isWritePermission
        }
        val info = queryDocument(root)
            ?: return mapOf(
                "status" to "provider_unavailable",
                "authorized" to true,
                "readable" to false,
                "writable" to writable,
                "error" to "文档目录授权仍在，但文档提供者当前不可用",
            )
        return mapOf(
            "status" to "ok",
            "authorized" to true,
            "display_name" to (info.name.ifEmpty { "已授权文档目录" }),
            "readable" to true,
            "writable" to writable,
        )
    }

    private fun revokeDocumentTree(): Map<String, Any?> {
        val raw = loadStoredTreeUri()
            ?: return mapOf("status" to "ok", "revoked" to false)
        releaseTreeGrant(Uri.parse(raw))
        removeStoredTreeUri()
        return mapOf("status" to "ok", "revoked" to true)
    }

    private fun listDocuments(arguments: Map<*, *>): Map<String, Any?> {
        val tree = authorizedTreeUri() ?: return treeNotAuthorized()
        val rawPath = arguments["path"]?.toString() ?: "."
        val maxEntries = integerArgument(arguments, "max_entries", 200, 1, 1000)
        val directory = resolveDocument(tree, rawPath)
            ?: return mapOf("status" to "not_found", "error" to "文档目录不存在")
        if (directory.mimeType != DocumentsContract.Document.MIME_TYPE_DIR) {
            return mapOf("status" to "invalid_target", "error" to "目标不是目录")
        }
        val childrenUri = DocumentsContract.buildChildDocumentsUriUsingTree(
            tree,
            DocumentsContract.getDocumentId(directory.uri),
        )
        val entries = mutableListOf<Map<String, Any?>>()
        val projection = arrayOf(
            DocumentsContract.Document.COLUMN_DOCUMENT_ID,
            DocumentsContract.Document.COLUMN_DISPLAY_NAME,
            DocumentsContract.Document.COLUMN_MIME_TYPE,
            DocumentsContract.Document.COLUMN_SIZE,
        )
        context.contentResolver.query(
            childrenUri,
            projection,
            null,
            null,
            null,
        )?.use { cursor ->
            val idIndex = cursor.getColumnIndexOrThrow(
                DocumentsContract.Document.COLUMN_DOCUMENT_ID
            )
            val nameIndex = cursor.getColumnIndexOrThrow(
                DocumentsContract.Document.COLUMN_DISPLAY_NAME
            )
            val mimeIndex = cursor.getColumnIndexOrThrow(
                DocumentsContract.Document.COLUMN_MIME_TYPE
            )
            val sizeIndex = cursor.getColumnIndex(
                DocumentsContract.Document.COLUMN_SIZE
            )
            while (cursor.moveToNext() && entries.size < maxEntries) {
                val id = cursor.getString(idIndex)
                val name = cursor.getString(nameIndex) ?: ""
                val mime = cursor.getString(mimeIndex) ?: "application/octet-stream"
                val size = if (sizeIndex >= 0 && !cursor.isNull(sizeIndex)) {
                    cursor.getLong(sizeIndex)
                } else {
                    null
                }
                // Constructing the URI validates that this is a child of the
                // persisted tree without exposing the provider's capability URI.
                DocumentsContract.buildDocumentUriUsingTree(tree, id)
                entries.add(
                    mapOf(
                        "name" to name,
                        "path" to joinRelativePath(rawPath, name),
                        "kind" to if (
                            mime == DocumentsContract.Document.MIME_TYPE_DIR
                        ) "directory" else "file",
                        "mime_type" to mime,
                        "size" to size,
                    )
                )
            }
        } ?: return mapOf(
            "status" to "permission_denied",
            "error" to "文档提供者拒绝列出目录",
        )
        return mapOf(
            "status" to "ok",
            "path" to normalizeRelativePath(rawPath).joinToString("/")
                .ifEmpty { "." },
            "entries" to entries,
            "truncated" to (entries.size >= maxEntries),
        )
    }

    private fun readDocument(arguments: Map<*, *>): Map<String, Any?> {
        val tree = authorizedTreeUri() ?: return treeNotAuthorized()
        val rawPath = arguments["path"]?.toString().orEmpty()
        val maxBytes = integerArgument(
            arguments,
            "max_bytes",
            262_144,
            1,
            MAX_TRANSFER_BYTES,
        )
        val document = resolveDocument(tree, rawPath)
            ?: return mapOf("status" to "not_found", "error" to "文档不存在")
        if (document.mimeType == DocumentsContract.Document.MIME_TYPE_DIR) {
            return mapOf("status" to "invalid_target", "error" to "目标不是文件")
        }
        val bytes = context.contentResolver.openInputStream(document.uri)?.use {
            readBounded(it, maxBytes)
        } ?: return mapOf(
            "status" to "permission_denied",
            "error" to "文档提供者拒绝读取文件",
        )
        return mapOf(
            "status" to "ok",
            "path" to normalizeRelativePath(rawPath).joinToString("/"),
            "name" to document.name,
            "mime_type" to document.mimeType,
            "content" to Base64.encodeToString(bytes, Base64.NO_WRAP),
            "encoding" to "base64",
            "size" to bytes.size,
            "sha256" to sha256(bytes),
        )
    }

    private fun writeDocument(arguments: Map<*, *>): Map<String, Any?> {
        val tree = authorizedTreeUri(requireWrite = true)
            ?: return mapOf(
                "status" to "permission_denied",
                "error" to "文档目录没有持久写入授权",
            )
        val rawPath = arguments["path"]?.toString().orEmpty()
        val expected = arguments["expected_sha256"]?.toString()
            ?.lowercase()?.trim().orEmpty()
        if (!expected.matches(Regex("[0-9a-f]{64}"))) {
            return mapOf(
                "status" to "failed",
                "error" to "expected_sha256 必须是 64 位十六进制摘要",
            )
        }
        val encoded = arguments["content"] as? String
            ?: return mapOf("status" to "failed", "error" to "content 必须是 base64")
        if (encoded.length > 1_398_104) {
            return mapOf("status" to "failed", "error" to "写入内容超过 1 MiB")
        }
        val replacement = try {
            Base64.decode(encoded, Base64.DEFAULT)
        } catch (_: IllegalArgumentException) {
            return mapOf("status" to "failed", "error" to "content 不是有效 base64")
        }
        if (replacement.size > MAX_TRANSFER_BYTES) {
            return mapOf("status" to "failed", "error" to "写入内容超过 1 MiB")
        }
        val document = resolveDocument(tree, rawPath)
            ?: return mapOf("status" to "not_found", "error" to "文档不存在")
        if (document.mimeType == DocumentsContract.Document.MIME_TYPE_DIR) {
            return mapOf("status" to "invalid_target", "error" to "目标不是文件")
        }
        val current = context.contentResolver.openInputStream(document.uri)?.use {
            readBounded(it, MAX_TRANSFER_BYTES)
        } ?: return mapOf(
            "status" to "permission_denied",
            "error" to "文档提供者拒绝读取当前内容",
        )
        val before = sha256(current)
        if (before != expected) {
            return mapOf(
                "status" to "conflict",
                "error" to "文件在审批前后已变化",
                "before_sha256" to before,
            )
        }
        val output = try {
            context.contentResolver.openOutputStream(document.uri, "rwt")
        } catch (_: Exception) {
            context.contentResolver.openOutputStream(document.uri, "w")
        }
            ?: return mapOf(
                "status" to "permission_denied",
                "error" to "文档提供者拒绝写入文件",
            )
        output.use {
            it.write(replacement)
            it.flush()
        }
        val persisted = context.contentResolver.openInputStream(document.uri)?.use {
            readBounded(it, MAX_TRANSFER_BYTES)
        } ?: return mapOf(
            "status" to "provider_mismatch",
            "error" to "文件已提交，但文档提供者拒绝回读验证",
            "before_sha256" to before,
        )
        val actualAfter = sha256(persisted)
        val requestedAfter = sha256(replacement)
        if (actualAfter != requestedAfter) {
            return mapOf(
                "status" to "provider_mismatch",
                "error" to "文档提供者写入后的内容与请求不一致",
                "before_sha256" to before,
                "after_sha256" to actualAfter,
                "requested_sha256" to requestedAfter,
            )
        }
        return mapOf(
            "status" to "applied",
            "path" to normalizeRelativePath(rawPath).joinToString("/"),
            "before_sha256" to before,
            "after_sha256" to actualAfter,
            "size" to replacement.size,
        )
    }

    private fun pickFile(
        arguments: Map<*, *>,
        result: MethodChannel.Result,
    ) {
        val host = activity
        if (host == null) {
            result.success(unavailableActivity())
            return
        }
        if (pendingActivity != null || pendingPermission != null) {
            result.success(busy())
            return
        }
        val maxBytes = try {
            integerArgument(
                arguments,
                "max_bytes",
                262_144,
                1,
                MAX_TRANSFER_BYTES,
            )
        } catch (error: Exception) {
            result.success(failed(error))
            return
        }
        val mime = arguments["mime_type"]?.toString()?.trim()
            ?.takeIf { it.isNotEmpty() }
            ?: "*/*"
        if (
            mime != "*/*" &&
            !mime.matches(Regex("[\\w.+-]+/[\\w.+*-]+"))
        ) {
            result.success(
                mapOf("status" to "failed", "error" to "mime_type 无效")
            )
            return
        }
        pendingActivity = PendingActivity("file", result, maxBytes)
        val intent = Intent(Intent.ACTION_OPEN_DOCUMENT).apply {
            addCategory(Intent.CATEGORY_OPENABLE)
            type = mime
            addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
        }
        try {
            host.startActivityForResult(intent, REQUEST_FILE)
        } catch (error: Exception) {
            pendingActivity = null
            result.success(failed(error))
        }
    }

    private fun capturePhoto(result: MethodChannel.Result) {
        val host = activity
        if (host == null) {
            result.success(unavailableActivity())
            return
        }
        if (pendingActivity != null || pendingPermission != null) {
            result.success(busy())
            return
        }
        val intent = Intent(MediaStore.ACTION_IMAGE_CAPTURE)
        if (intent.resolveActivity(context.packageManager) == null) {
            result.success(
                mapOf("status" to "unavailable", "error" to "没有可用的相机 App")
            )
            return
        }
        pendingActivity = PendingActivity("camera", result)
        try {
            host.startActivityForResult(intent, REQUEST_CAMERA)
        } catch (error: Exception) {
            pendingActivity = null
            result.success(failed(error))
        }
    }

    private fun shareText(
        arguments: Map<*, *>,
        result: MethodChannel.Result,
    ) {
        val host = activity
        if (host == null) {
            result.success(unavailableActivity())
            return
        }
        val text = arguments["text"]?.toString().orEmpty()
        if (text.isEmpty() || text.length > 100_000) {
            result.success(
                mapOf(
                    "status" to "failed",
                    "error" to "分享文本长度必须为 1–100000",
                )
            )
            return
        }
        val title = arguments["title"]?.toString()?.take(120) ?: "通过…分享"
        val intent = Intent(Intent.ACTION_SEND).apply {
            type = "text/plain"
            putExtra(Intent.EXTRA_TEXT, text)
            arguments["subject"]?.toString()?.takeIf { it.isNotEmpty() }?.let {
                putExtra(Intent.EXTRA_SUBJECT, it.take(200))
            }
        }
        try {
            host.startActivity(Intent.createChooser(intent, title))
            result.success(mapOf("status" to "launched"))
        } catch (error: Exception) {
            result.success(failed(error))
        }
    }

    override fun onActivityResult(
        requestCode: Int,
        resultCode: Int,
        data: Intent?,
    ): Boolean {
        val expectedKind = when (requestCode) {
            REQUEST_TREE -> "tree"
            REQUEST_FILE -> "file"
            REQUEST_CAMERA -> "camera"
            else -> return false
        }
        val pending = pendingActivity ?: return true
        if (pending.kind != expectedKind) return true
        pendingActivity = null
        if (resultCode != Activity.RESULT_OK) {
            pending.result.success(mapOf("status" to "cancelled"))
            return true
        }
        when (expectedKind) {
            "tree" -> finishTreeSelection(data, pending.result)
            "file" -> finishFileSelection(data, pending)
            "camera" -> finishCamera(data, pending.result)
        }
        return true
    }

    private fun finishTreeSelection(
        data: Intent?,
        result: MethodChannel.Result,
    ) {
        val returnedIntent = data
        if (returnedIntent == null) {
            result.success(mapOf("status" to "cancelled"))
            return
        }
        val uri = returnedIntent.data
        if (uri == null) {
            result.success(mapOf("status" to "cancelled"))
            return
        }
        if (
            uri.scheme != "content" ||
            !DocumentsContract.isTreeUri(uri)
        ) {
            result.success(
                mapOf(
                    "status" to "permission_denied",
                    "error" to "系统选择器没有返回有效的文档树授权",
                )
            )
            return
        }
        val flags = (returnedIntent.flags and (
            Intent.FLAG_GRANT_READ_URI_PERMISSION or
                Intent.FLAG_GRANT_WRITE_URI_PERMISSION
            ))
        if (flags and Intent.FLAG_GRANT_READ_URI_PERMISSION == 0) {
            result.success(
                mapOf(
                    "status" to "permission_denied",
                    "error" to "文档提供者没有授予读取权限",
                )
            )
            return
        }
        try {
            val previous = loadStoredTreeUri()?.let(Uri::parse)
            context.contentResolver.takePersistableUriPermission(uri, flags)
            try {
                saveStoredTreeUri(uri.toString())
            } catch (error: Exception) {
                releaseTreeGrant(uri)
                throw error
            }
            if (previous != null && previous != uri) {
                releaseTreeGrant(previous)
            }
            runIo(result) { documentTreeStatus() }
        } catch (error: SecurityException) {
            result.success(permissionDenied(error))
        } catch (error: Exception) {
            result.success(failed(error))
        }
    }

    private fun finishFileSelection(data: Intent?, pending: PendingActivity) {
        val uri = data?.data
        if (uri == null) {
            pending.result.success(mapOf("status" to "cancelled"))
            return
        }
        runIo(pending.result) {
            val info = queryDocument(uri)
            val bytes = context.contentResolver.openInputStream(uri)?.use {
                readBounded(it, pending.maxBytes)
            } ?: return@runIo mapOf(
                "status" to "permission_denied",
                "error" to "文档提供者拒绝读取所选文件",
            )
            mapOf(
                "status" to "ok",
                "name" to (info?.name ?: "selected-file"),
                "mime_type" to (
                    info?.mimeType
                        ?: context.contentResolver.getType(uri)
                        ?: "application/octet-stream"
                    ),
                "content" to Base64.encodeToString(bytes, Base64.NO_WRAP),
                "encoding" to "base64",
                "size" to bytes.size,
                "sha256" to sha256(bytes),
            )
        }
    }

    private fun finishCamera(data: Intent?, result: MethodChannel.Result) {
        @Suppress("DEPRECATION")
        val bitmap = data?.extras?.get("data") as? Bitmap
        if (bitmap == null) {
            result.success(
                mapOf(
                    "status" to "failed",
                    "error" to "相机没有返回照片缩略图",
                )
            )
            return
        }
        executor.execute {
            try {
                val output = ByteArrayOutputStream()
                bitmap.compress(Bitmap.CompressFormat.JPEG, 92, output)
                val bytes = output.toByteArray()
                require(bytes.size <= MAX_TRANSFER_BYTES) {
                    "相机返回的缩略图超过 1 MiB"
                }
                val response = mapOf(
                    "status" to "ok",
                    "name" to "camera-${System.currentTimeMillis()}.jpg",
                    "mime_type" to "image/jpeg",
                    "content" to Base64.encodeToString(bytes, Base64.NO_WRAP),
                    "encoding" to "base64",
                    "size" to bytes.size,
                    "sha256" to sha256(bytes),
                    "width" to bitmap.width,
                    "height" to bitmap.height,
                )
                mainHandler.post { result.success(response) }
            } catch (error: Exception) {
                mainHandler.post { result.success(failed(error)) }
            }
        }
    }

    private fun authorizedTreeUri(requireWrite: Boolean = false): Uri? {
        val raw = loadStoredTreeUri() ?: return null
        val uri = try {
            Uri.parse(raw)
        } catch (_: Exception) {
            removeStoredTreeUri()
            return null
        }
        if (
            uri.scheme != "content" ||
            !DocumentsContract.isTreeUri(uri)
        ) {
            removeStoredTreeUri()
            return null
        }
        val permission = context.contentResolver.persistedUriPermissions.firstOrNull {
            it.uri == uri && it.isReadPermission && (!requireWrite || it.isWritePermission)
        }
        if (permission == null && !requireWrite) {
            removeStoredTreeUri()
        }
        return if (permission != null) uri else null
    }

    private fun loadStoredTreeUri(): String? {
        var encrypted: ByteArray? = null
        try {
            encrypted = secureStore.get(TREE_RECORD)
            if (encrypted != null) {
                return encrypted.toString(Charsets.UTF_8)
            }
        } finally {
            encrypted?.fill(0)
        }

        // Migrate Phase 7 development builds which briefly stored the selected
        // URI in ordinary app-private preferences.
        val preferences =
            context.getSharedPreferences("cloudra_native_state", Context.MODE_PRIVATE)
        val legacy = preferences.getString(LEGACY_TREE_PREF, null) ?: return null
        saveStoredTreeUri(legacy)
        preferences.edit().remove(LEGACY_TREE_PREF).apply()
        return legacy
    }

    private fun saveStoredTreeUri(raw: String) {
        val bytes = raw.toByteArray(Charsets.UTF_8)
        try {
            secureStore.set(TREE_RECORD, bytes)
        } finally {
            bytes.fill(0)
        }
        val preferences =
            context.getSharedPreferences("cloudra_native_state", Context.MODE_PRIVATE)
        preferences.edit().remove(LEGACY_TREE_PREF).apply()
    }

    private fun removeStoredTreeUri() {
        secureStore.remove(TREE_RECORD)
        val preferences =
            context.getSharedPreferences("cloudra_native_state", Context.MODE_PRIVATE)
        preferences.edit().remove(LEGACY_TREE_PREF).apply()
    }

    private fun releaseTreeGrant(uri: Uri) {
        val permission = context.contentResolver.persistedUriPermissions.firstOrNull {
            it.uri == uri
        } ?: return
        var flags = 0
        if (permission.isReadPermission) {
            flags = flags or Intent.FLAG_GRANT_READ_URI_PERMISSION
        }
        if (permission.isWritePermission) {
            flags = flags or Intent.FLAG_GRANT_WRITE_URI_PERMISSION
        }
        if (flags == 0) return
        try {
            context.contentResolver.releasePersistableUriPermission(uri, flags)
        } catch (_: SecurityException) {
            // The provider may revoke the grant between inspection and release.
        }
    }

    private fun rootDocument(tree: Uri): Uri =
        DocumentsContract.buildDocumentUriUsingTree(
            tree,
            DocumentsContract.getTreeDocumentId(tree),
        )

    private fun resolveDocument(tree: Uri, rawPath: String): DocumentInfo? {
        val parts = normalizeRelativePath(rawPath)
        var current = queryDocument(rootDocument(tree)) ?: return null
        for (part in parts) {
            if (current.mimeType != DocumentsContract.Document.MIME_TYPE_DIR) {
                return null
            }
            current = findChild(tree, current.uri, part) ?: return null
        }
        return current
    }

    private fun findChild(tree: Uri, parent: Uri, name: String): DocumentInfo? {
        val children = DocumentsContract.buildChildDocumentsUriUsingTree(
            tree,
            DocumentsContract.getDocumentId(parent),
        )
        val projection = arrayOf(
            DocumentsContract.Document.COLUMN_DOCUMENT_ID,
            DocumentsContract.Document.COLUMN_DISPLAY_NAME,
            DocumentsContract.Document.COLUMN_MIME_TYPE,
            DocumentsContract.Document.COLUMN_SIZE,
        )
        context.contentResolver.query(children, projection, null, null, null)
            ?.use { cursor ->
                val idIndex = cursor.getColumnIndexOrThrow(
                    DocumentsContract.Document.COLUMN_DOCUMENT_ID
                )
                val nameIndex = cursor.getColumnIndexOrThrow(
                    DocumentsContract.Document.COLUMN_DISPLAY_NAME
                )
                val mimeIndex = cursor.getColumnIndexOrThrow(
                    DocumentsContract.Document.COLUMN_MIME_TYPE
                )
                val sizeIndex = cursor.getColumnIndex(
                    DocumentsContract.Document.COLUMN_SIZE
                )
                while (cursor.moveToNext()) {
                    if (cursor.getString(nameIndex) != name) continue
                    val uri = DocumentsContract.buildDocumentUriUsingTree(
                        tree,
                        cursor.getString(idIndex),
                    )
                    return DocumentInfo(
                        uri,
                        name,
                        cursor.getString(mimeIndex) ?: "application/octet-stream",
                        if (sizeIndex >= 0 && !cursor.isNull(sizeIndex)) {
                            cursor.getLong(sizeIndex)
                        } else {
                            null
                        },
                    )
                }
            }
        return null
    }

    private fun queryDocument(uri: Uri): DocumentInfo? {
        val projection = arrayOf(
            OpenableColumns.DISPLAY_NAME,
            DocumentsContract.Document.COLUMN_MIME_TYPE,
            OpenableColumns.SIZE,
        )
        context.contentResolver.query(uri, projection, null, null, null)?.use { cursor ->
            if (!cursor.moveToFirst()) return null
            val nameIndex = cursor.getColumnIndex(OpenableColumns.DISPLAY_NAME)
            val mimeIndex = cursor.getColumnIndex(
                DocumentsContract.Document.COLUMN_MIME_TYPE
            )
            val sizeIndex = cursor.getColumnIndex(OpenableColumns.SIZE)
            return DocumentInfo(
                uri,
                if (nameIndex >= 0) cursor.getString(nameIndex) ?: "" else "",
                if (mimeIndex >= 0) {
                    cursor.getString(mimeIndex) ?: "application/octet-stream"
                } else {
                    context.contentResolver.getType(uri) ?: "application/octet-stream"
                },
                if (sizeIndex >= 0 && !cursor.isNull(sizeIndex)) {
                    cursor.getLong(sizeIndex)
                } else {
                    null
                },
            )
        }
        return null
    }

    private fun normalizeRelativePath(raw: String): List<String> {
        require(raw.length <= 4096)
        val path = raw.trim()
        require(!path.startsWith("/") && !path.startsWith("\\"))
        require(!path.contains('\\') && !path.contains('\u0000'))
        if (path.isEmpty() || path == ".") return emptyList()
        val parts = path.split("/")
        require(parts.size <= 64)
        for (part in parts) {
            require(part.isNotEmpty() && part != "." && part != "..")
            require(part.length <= 255 && !part.any { it.code < 32 })
        }
        return parts
    }

    private fun joinRelativePath(parent: String, child: String): String {
        val prefix = normalizeRelativePath(parent).joinToString("/")
        return if (prefix.isEmpty()) child else "$prefix/$child"
    }

    private fun readBounded(input: java.io.InputStream, maxBytes: Int): ByteArray {
        val output = ByteArrayOutputStream()
        val buffer = ByteArray(8192)
        while (true) {
            val read = input.read(buffer)
            if (read < 0) break
            if (output.size() + read > maxBytes) {
                throw IllegalArgumentException("文件超过本次读取上限 $maxBytes bytes")
            }
            output.write(buffer, 0, read)
        }
        return output.toByteArray()
    }

    private fun integerArgument(
        arguments: Map<*, *>,
        name: String,
        defaultValue: Int,
        minimum: Int,
        maximum: Int,
    ): Int {
        val raw = arguments[name] ?: return defaultValue
        val value = when (raw) {
            is Number -> raw.toInt()
            else -> raw.toString().toInt()
        }
        require(value in minimum..maximum) {
            "$name 必须在 $minimum–$maximum 之间"
        }
        return value
    }

    private fun sha256(bytes: ByteArray): String =
        MessageDigest.getInstance("SHA-256")
            .digest(bytes)
            .joinToString("") { "%02x".format(it) }

    private fun runIo(
        result: MethodChannel.Result,
        block: () -> Map<String, Any?>,
    ) {
        executor.execute {
            val response = try {
                block()
            } catch (error: SecurityException) {
                permissionDenied(error)
            } catch (error: Exception) {
                failed(error)
            }
            mainHandler.post { result.success(response) }
        }
    }

    private fun treeNotAuthorized(): Map<String, Any?> = mapOf(
        "status" to "not_authorized",
        "error" to "请先在 Android 上授权一个文档目录",
    )

    private fun unavailableActivity(): Map<String, Any?> = mapOf(
        "status" to "unavailable",
        "error" to "Android Activity 当前不可用，请点按通知返回 Cloudra",
    )

    private fun busy(): Map<String, Any?> = mapOf(
        "status" to "busy",
        "error" to "已有一个 Android 系统交互正在等待用户处理",
    )

    private fun failed(error: Exception): Map<String, Any?> = mapOf(
        "status" to "failed",
        "error" to safeError(error),
    )

    private fun permissionDenied(error: Exception): Map<String, Any?> = mapOf(
        "status" to "permission_denied",
        "error" to safeError(error),
    )

    private fun safeError(error: Exception): String =
        (error.message ?: error.javaClass.simpleName)
            .replace(Regex("content://\\S+"), "content://<redacted>")
            .take(500)
}

private class SecureTransport {
    companion object {
        private const val KEYSTORE = "AndroidKeyStore"
        private const val ALIAS = "cloudra.bridge.transport.v1"
        private const val SESSION_MILLIS = 15 * 60 * 1000L
        private const val MAX_SESSIONS = 8
        private const val MAX_ENCODED_VALUE = 1_398_104
        private val ENC_PREFIX =
            "cloudra-transport-v1:enc:".toByteArray(Charsets.UTF_8)
        private val TAG_PREFIX =
            "cloudra-transport-v1:tag:".toByteArray(Charsets.UTF_8)
    }

    class SessionExpired : Exception()

    private data class Session(
        val key: ByteArray,
        val expiresAt: Long,
    )

    private val sessions = linkedMapOf<String, Session>()
    private val random = java.security.SecureRandom()

    private fun keyStore(): KeyStore =
        KeyStore.getInstance(KEYSTORE).apply { load(null) }

    private fun ensureKeyPair(): Pair<java.security.PrivateKey, RSAPublicKey> {
        var store = keyStore()
        if (!store.containsAlias(ALIAS)) {
            val generator = KeyPairGenerator.getInstance(
                KeyProperties.KEY_ALGORITHM_RSA,
                KEYSTORE,
            )
            generator.initialize(
                KeyGenParameterSpec.Builder(
                    ALIAS,
                    KeyProperties.PURPOSE_DECRYPT,
                )
                    .setKeySize(2048)
                    .setDigests(
                        KeyProperties.DIGEST_SHA256,
                        KeyProperties.DIGEST_SHA1,
                    )
                    .setEncryptionPaddings(
                        KeyProperties.ENCRYPTION_PADDING_RSA_OAEP
                    )
                    .build()
            )
            generator.generateKeyPair()
            store = keyStore()
        }
        val privateKey = store.getKey(
            ALIAS,
            null,
        ) as? java.security.PrivateKey
            ?: throw IllegalStateException("Keystore RSA private key unavailable")
        val publicKey = store.getCertificate(ALIAS)?.publicKey as? RSAPublicKey
            ?: throw IllegalStateException("Keystore RSA public key unavailable")
        return privateKey to publicKey
    }

    fun publicKey(): Map<String, Any> {
        val publicKey = ensureKeyPair().second
        val encodedModulus = publicKey.modulus.toByteArray().let {
            if (it.size > 1 && it[0] == 0.toByte()) {
                it.copyOfRange(1, it.size)
            } else {
                it
            }
        }
        return mapOf(
            "status" to "ok",
            "algorithm" to "RSA-OAEP-SHA256-MGF1-SHA1",
            "modulus" to Base64.encodeToString(
                encodedModulus,
                Base64.NO_WRAP,
            ),
            "exponent" to publicKey.publicExponent.toLong(),
        )
    }

    @Synchronized
    fun openSession(wrappedBase64: String): String {
        require(wrappedBase64.length <= 512)
        val wrapped = Base64.decode(wrappedBase64, Base64.DEFAULT)
        val privateKey = ensureKeyPair().first
        val cipher = Cipher.getInstance(
            "RSA/ECB/OAEPWithSHA-256AndMGF1Padding"
        )
        cipher.init(
            Cipher.DECRYPT_MODE,
            privateKey,
            OAEPParameterSpec(
                "SHA-256",
                "MGF1",
                MGF1ParameterSpec.SHA1,
                PSource.PSpecified.DEFAULT,
            ),
        )
        val sessionKey = cipher.doFinal(wrapped)
        require(sessionKey.size == 32)
        purgeExpired()
        while (sessions.size >= MAX_SESSIONS) {
            val oldest = sessions.entries.minByOrNull {
                it.value.expiresAt
            } ?: break
            sessions.remove(oldest.key)?.key?.fill(0)
        }
        val sessionId = "sec_${java.util.UUID.randomUUID()}"
        sessions[sessionId] = Session(
            sessionKey.copyOf(),
            SystemClock.elapsedRealtime() + SESSION_MILLIS,
        )
        sessionKey.fill(0)
        return sessionId
    }

    @Synchronized
    private fun purgeExpired() {
        val now = SystemClock.elapsedRealtime()
        val expired = sessions.filterValues {
            it.expiresAt <= now
        }.keys
        for (sessionId in expired) {
            sessions.remove(sessionId)?.key?.fill(0)
        }
    }

    @Synchronized
    fun clear() {
        for (session in sessions.values) {
            session.key.fill(0)
        }
        sessions.clear()
    }

    @Synchronized
    private fun sessionKey(sessionId: String): ByteArray {
        purgeExpired()
        val session = sessions[sessionId] ?: throw SessionExpired()
        return session.key.copyOf()
    }

    fun requireSession(arguments: Map<*, *>) {
        val sessionId = arguments["session_id"]?.toString().orEmpty()
        val key = sessionKey(sessionId)
        key.fill(0)
    }

    fun openEnvelope(
        arguments: Map<*, *>,
        aad: ByteArray = ByteArray(0),
    ): ByteArray {
        val sessionId = arguments["session_id"]?.toString().orEmpty()
        val key = sessionKey(sessionId)
        try {
            val nonce = decode(arguments, "nonce", 64)
            val ciphertext = decode(
                arguments,
                "ciphertext",
                MAX_ENCODED_VALUE,
            )
            val tag = decode(arguments, "tag", 128)
            require(nonce.size == 16 && tag.size == 32)
            val expected = hmac(
                key,
                tagPayload(aad, nonce, ciphertext),
            )
            require(MessageDigest.isEqual(expected, tag)) {
                "secure transport integrity check failed"
            }
            return xor(
                ciphertext,
                stream(key, nonce, ciphertext.size),
            )
        } finally {
            key.fill(0)
        }
    }

    fun sealEnvelope(
        arguments: Map<*, *>,
        plaintext: ByteArray,
        aad: ByteArray = ByteArray(0),
    ): Map<String, String> {
        val sessionId = arguments["session_id"]?.toString().orEmpty()
        val key = sessionKey(sessionId)
        try {
            val nonce = ByteArray(16).also { random.nextBytes(it) }
            val ciphertext = xor(
                plaintext,
                stream(key, nonce, plaintext.size),
            )
            val tag = hmac(
                key,
                tagPayload(aad, nonce, ciphertext),
            )
            return mapOf(
                "nonce" to Base64.encodeToString(nonce, Base64.NO_WRAP),
                "ciphertext" to Base64.encodeToString(
                    ciphertext,
                    Base64.NO_WRAP,
                ),
                "tag" to Base64.encodeToString(tag, Base64.NO_WRAP),
            )
        } finally {
            key.fill(0)
        }
    }

    private fun tagPayload(
        aad: ByteArray,
        nonce: ByteArray,
        ciphertext: ByteArray,
    ): ByteArray =
        TAG_PREFIX +
            ByteBuffer.allocate(4).putInt(aad.size).array() +
            aad +
            nonce +
            ciphertext

    private fun decode(
        arguments: Map<*, *>,
        name: String,
        maxEncodedLength: Int,
    ): ByteArray {
        val value = arguments[name] as? String
            ?: throw IllegalArgumentException("$name must be base64")
        require(value.length <= maxEncodedLength)
        return Base64.decode(value, Base64.DEFAULT)
    }

    private fun stream(
        key: ByteArray,
        nonce: ByteArray,
        length: Int,
    ): ByteArray {
        val output = ByteArray(length)
        var offset = 0
        var counter = 0
        while (offset < length) {
            val counterBytes = ByteBuffer.allocate(4).putInt(counter).array()
            val block = hmac(
                key,
                ENC_PREFIX + nonce + counterBytes,
            )
            val count = minOf(block.size, length - offset)
            block.copyInto(output, offset, 0, count)
            offset += count
            counter += 1
        }
        return output
    }

    private fun hmac(key: ByteArray, data: ByteArray): ByteArray {
        val mac = Mac.getInstance("HmacSHA256")
        mac.init(SecretKeySpec(key, "HmacSHA256"))
        return mac.doFinal(data)
    }

    private fun xor(left: ByteArray, right: ByteArray): ByteArray {
        require(left.size == right.size)
        return ByteArray(left.size) { index ->
            (left[index].toInt() xor right[index].toInt()).toByte()
        }
    }
}

private class KeystoreStore(context: Context) {
    companion object {
        private const val KEYSTORE = "AndroidKeyStore"
        private const val ALIAS = "cloudra.runtime.credentials.v1"
        private const val PREFIX_V1 = "v1"
        private const val PREFIX_V2 = "v2"
    }

    private val preferences =
        context.getSharedPreferences("cloudra_secure_credentials", Context.MODE_PRIVATE)

    private fun secretKey(): SecretKey {
        val store = KeyStore.getInstance(KEYSTORE).apply { load(null) }
        (store.getKey(ALIAS, null) as? SecretKey)?.let { return it }
        val generator = KeyGenerator.getInstance(
            KeyProperties.KEY_ALGORITHM_AES,
            KEYSTORE,
        )
        generator.init(
            KeyGenParameterSpec.Builder(
                ALIAS,
                KeyProperties.PURPOSE_ENCRYPT or KeyProperties.PURPOSE_DECRYPT,
            )
                .setBlockModes(KeyProperties.BLOCK_MODE_GCM)
                .setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE)
                .setRandomizedEncryptionRequired(true)
                .build()
        )
        return generator.generateKey()
    }

    fun set(key: String, value: ByteArray) {
        val cipher = Cipher.getInstance("AES/GCM/NoPadding")
        cipher.init(Cipher.ENCRYPT_MODE, secretKey())
        cipher.updateAAD(key.toByteArray(Charsets.UTF_8))
        val encrypted = cipher.doFinal(value)
        val payload = listOf(
            PREFIX_V2,
            Base64.encodeToString(cipher.iv, Base64.NO_WRAP),
            Base64.encodeToString(encrypted, Base64.NO_WRAP),
        ).joinToString(":")
        check(preferences.edit().putString(key, payload).commit()) {
            "secure storage commit failed"
        }
    }

    fun get(key: String): ByteArray? {
        val payload = preferences.getString(key, null) ?: return null
        val parts = payload.split(":")
        if (
            parts.size != 3 ||
            parts[0] !in setOf(PREFIX_V1, PREFIX_V2)
        ) {
            throw IllegalStateException("unsupported secure-storage record")
        }
        val iv = Base64.decode(parts[1], Base64.NO_WRAP)
        val encrypted = Base64.decode(parts[2], Base64.NO_WRAP)
        val cipher = Cipher.getInstance("AES/GCM/NoPadding")
        cipher.init(
            Cipher.DECRYPT_MODE,
            secretKey(),
            GCMParameterSpec(128, iv),
        )
        if (parts[0] == PREFIX_V2) {
            cipher.updateAAD(key.toByteArray(Charsets.UTF_8))
        }
        val plaintext = cipher.doFinal(encrypted)
        if (parts[0] == PREFIX_V1) {
            // Bind development-build records to their logical key the first
            // time they are read.
            set(key, plaintext)
        }
        return plaintext
    }

    fun remove(key: String): Boolean {
        val existed = preferences.contains(key)
        check(preferences.edit().remove(key).commit()) {
            "secure storage commit failed"
        }
        return existed
    }

    fun contains(key: String): Boolean = preferences.contains(key)
}
