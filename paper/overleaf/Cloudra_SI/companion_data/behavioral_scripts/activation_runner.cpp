// Offline, same-GGUF forward pass. Patches live GGML tensors, never weights or getter copies.
#include "llama.h"
#include "ggml-backend.h"
#include "json.hpp"
#include <algorithm>
#include <cmath>
#include <cstring>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <iterator>
#include <map>
#include <memory>
#include <numeric>
#include <set>
#include <stdexcept>
#include <string>
#include <vector>

using json = nlohmann::ordered_json;
namespace fs = std::filesystem;

static std::string read_text(const fs::path & path) {
    std::ifstream input(path, std::ios::binary);
    if (!input) throw std::runtime_error("Cannot read " + path.string());
    return {std::istreambuf_iterator<char>(input), std::istreambuf_iterator<char>()};
}
static void write_f32(const fs::path & path, const std::vector<float> & values) {
    std::ofstream output(path, std::ios::binary);
    output.write(reinterpret_cast<const char *>(values.data()), values.size() * sizeof(float));
    if (!output) throw std::runtime_error("Cannot write " + path.string());
}
static json describe(const ggml_tensor * t) {
    json result = {{"name", t->name}, {"type", ggml_type_name(t->type)}, {"shape", json::array()},
                   {"strides_bytes", json::array()}};
    for (int i = 0; i < GGML_MAX_DIMS; ++i) {
        result["shape"].push_back(t->ne[i]);
        result["strides_bytes"].push_back(t->nb[i]);
    }
    return result;
}
struct Hooks {
    fs::path out;
    std::set<std::string> capture_names;
    std::string patch_name;
    std::vector<float> patch;
    int token_count = 0;
    int requested_token_position = -1; // -1 means the default last input token.
    int global_token_position = -1;
    int patch_physical_row = -1;
    bool enumerate = false;
    bool patch_applied = false;
    std::string error;
    std::map<std::string, json> tensors;
    json captures = json::array();
};
static bool evaluate(ggml_tensor * t, bool ask, void * user_data) {
    auto & hooks = *static_cast<Hooks *>(user_data);
    const std::string name(t->name);
    const bool capture = hooks.capture_names.count(name) != 0;
    const bool patch = name == hooks.patch_name;
    if (ask) {
        if (hooks.enumerate) hooks.tensors[name] = describe(t);
        return capture || patch;
    }
    try {
        // This runner feeds exactly one sequence and one microbatch. The last layer
        // may keep only its final row because only that token requests logits.
        if (t->type != GGML_TYPE_F32 || t->ne[2] != 1 || t->ne[3] != 1 ||
            t->nb[0] != sizeof(float) || (t->ne[1] != hooks.token_count && t->ne[1] != 1)) {
            throw std::runtime_error("Expected F32 [embedding, tokens] residual tensor: " + name);
        }
        if (t->ne[1] == 1 && hooks.global_token_position != hooks.token_count - 1) {
            throw std::runtime_error("Tensor retains only the last token; cannot select input position " +
                                     std::to_string(hooks.global_token_position) + ": " + name);
        }
        const size_t row = t->ne[1] == hooks.token_count ? hooks.global_token_position : 0;
        const size_t offset = row * t->nb[1];
        const size_t bytes = t->ne[0] * sizeof(float);
        std::vector<float> values(t->ne[0]);
        if (patch) {
            if (hooks.patch.size() != values.size()) throw std::runtime_error("Patch vector has wrong dimension");
            // The scheduler synchronized this node before calling ask=false.
            // Write to the live backend tensor before downstream graph evaluation.
            ggml_backend_tensor_set(t, hooks.patch.data(), offset, bytes);
            hooks.patch_applied = true;
            hooks.patch_physical_row = row;
        }
        if (capture || patch) ggml_backend_tensor_get(t, values.data(), offset, bytes);
        if (patch && values != hooks.patch) throw std::runtime_error("Live tensor patch readback differs");
        if (capture) {
            const std::string layer = name.substr(std::string("l_out-").size());
            const fs::path path = hooks.out / ("capture-" + layer + ".f32");
            write_f32(path, values);
            json metadata = describe(t);
            metadata["path"] = fs::absolute(path).string();
            metadata["requested_token_position"] = hooks.requested_token_position < 0
                ? json("last") : json(hooks.requested_token_position);
            metadata["global_token_position"] = hooks.global_token_position;
            metadata["physical_row"] = row;
            metadata["after_patch"] = patch;
            hooks.captures.push_back(metadata);
        }
    } catch (const std::exception & e) {
        hooks.error = e.what();
        return false;
    }
    return true;
}
static std::string token_piece(const llama_vocab * vocab, llama_token token) {
    std::vector<char> buffer(256);
    int n = llama_token_to_piece(vocab, token, buffer.data(), buffer.size(), 0, true);
    if (n < 0) {
        buffer.resize(-n);
        n = llama_token_to_piece(vocab, token, buffer.data(), buffer.size(), 0, true);
    }
    if (n < 0) throw std::runtime_error("Cannot decode token");
    return {buffer.data(), static_cast<size_t>(n)};
}
static std::string bytes_hex(const std::string & bytes) {
    const char * digits = "0123456789abcdef";
    std::string result;
    result.reserve(bytes.size() * 2);
    for (unsigned char byte : bytes) {
        result.push_back(digits[byte >> 4]);
        result.push_back(digits[byte & 15]);
    }
    return result;
}
int main(int argc, char ** argv) {
    try {
        std::string model_path, prompt_path, out_path, patch_path;
        int gpu_layers = 99, patch_layer = -1, token_position = -1;
        std::set<int> capture_layers;
        bool enumerate = false, tokenize_only = false;
        for (int i = 1; i < argc; ++i) {
            const std::string arg(argv[i]);
            if (arg == "--help") {
                std::cout << "activation_runner --model GGUF --prompt UTF8_FILE --out DIR\n"
                             "  [--gpu-layers N] [--capture LAYER,LAYER] [--list-tensors]\n"
                             "  [--patch CAPTURE.f32 --patch-layer LAYER]\n"
                             "  [--token-position N] (default: last input token)\n"
                             "  [--tokenize-only] (vocabulary only; no backend or context)\n"
                             "One raw prompt, one microbatch; no generation or MTP.\n";
                return 0;
            }
            if (arg == "--list-tensors") { enumerate = true; continue; }
            if (arg == "--tokenize-only") { tokenize_only = true; continue; }
            if (i + 1 == argc) throw std::runtime_error("Missing value for " + arg);
            const std::string value(argv[++i]);
            if (arg == "--model") model_path = value;
            else if (arg == "--prompt") prompt_path = value;
            else if (arg == "--out") out_path = value;
            else if (arg == "--gpu-layers") gpu_layers = std::stoi(value);
            else if (arg == "--patch") patch_path = value;
            else if (arg == "--patch-layer") patch_layer = std::stoi(value);
            else if (arg == "--token-position") {
                token_position = std::stoi(value);
                if (token_position < 0) throw std::runtime_error("Token position must be nonnegative");
            }
            else if (arg == "--capture") {
                size_t start = 0;
                while (start < value.size()) {
                    const size_t end = value.find(',', start);
                    capture_layers.insert(std::stoi(value.substr(start, end - start)));
                    if (end == std::string::npos) break;
                    start = end + 1;
                }
            } else throw std::runtime_error("Unknown option: " + arg);
        }
        if (model_path.empty() || prompt_path.empty() || out_path.empty())
            throw std::runtime_error("Required: --model GGUF --prompt UTF8_FILE --out DIR");
        if (patch_path.empty() != (patch_layer < 0))
            throw std::runtime_error("Use --patch and --patch-layer together");
        fs::create_directories(out_path);
        Hooks hooks;
        hooks.out = out_path;
        hooks.enumerate = enumerate;
        hooks.requested_token_position = token_position;
        for (int layer : capture_layers) {
            if (layer < 0) throw std::runtime_error("Capture layer must be nonnegative");
            hooks.capture_names.insert("l_out-" + std::to_string(layer));
        }
        if (!patch_path.empty()) {
            const std::string data = read_text(patch_path);
            if (data.empty() || data.size() % sizeof(float)) throw std::runtime_error("Patch must be nonempty binary F32");
            hooks.patch.resize(data.size() / sizeof(float));
            std::memcpy(hooks.patch.data(), data.data(), data.size());
            hooks.patch_name = "l_out-" + std::to_string(patch_layer);
        }
        const std::string prompt = read_text(prompt_path);
        if (!tokenize_only) {
            ggml_backend_load_all();
            llama_backend_init();
        }
        auto mp = llama_model_default_params();
        ggml_backend_dev_t no_devices[] = {nullptr};
        if (tokenize_only) mp.devices = no_devices; // Skip default device enumeration, including Metal.
        mp.n_gpu_layers = tokenize_only ? 0 : gpu_layers;
        mp.vocab_only = tokenize_only;
        mp.load_mtp = false;
        std::unique_ptr<llama_model, decltype(&llama_model_free)> model(
            llama_model_load_from_file(model_path.c_str(), mp), llama_model_free);
        if (!model) throw std::runtime_error("Model load failed");
        const llama_vocab * vocab = llama_model_get_vocab(model.get());
        int count = -llama_tokenize(vocab, prompt.data(), prompt.size(), nullptr, 0, true, true);
        if (count <= 0) throw std::runtime_error("Prompt has no tokens");
        std::vector<llama_token> tokens(count);
        count = llama_tokenize(vocab, prompt.data(), prompt.size(), tokens.data(), tokens.size(), true, true);
        if (count <= 0) throw std::runtime_error("Tokenization failed");
        tokens.resize(count);
        json input_token_bytes_hex = json::array();
        for (llama_token token : tokens) input_token_bytes_hex.push_back(bytes_hex(token_piece(vocab, token)));
        if (tokenize_only) {
            char context_length[64] = {};
            llama_model_meta_val_str(model.get(), "qwen35.context_length", context_length, sizeof(context_length));
            json metadata = {{"runner_commit", "9d77fa172"}, {"mode", "tokenize_only"},
                {"model_path", fs::absolute(model_path).string()}, {"prompt_path", fs::absolute(prompt_path).string()},
                {"prompt_utf8_bytes", prompt.size()}, {"token_count", count}, {"token_ids", tokens},
                {"input_token_bytes_hex", input_token_bytes_hex}, {"vocab_size", llama_vocab_n_tokens(vocab)},
                {"tokenization", {{"add_special", true}, {"parse_special", true}}},
                {"context_length_metadata", context_length}, {"weights_loaded", false},
                {"backend_initialized", false}, {"devices_enumerated", false}, {"context_created", false},
                {"interpretation", "Token count of the supplied raw file, not reconstructed provider wire/chat input"}};
            std::ofstream output(hooks.out / "metadata.json");
            output << metadata.dump(2) << '\n';
            if (!output) throw std::runtime_error("Cannot write tokenization metadata");
            std::cout << (fs::absolute(hooks.out) / "metadata.json").string() << '\n';
            return 0;
        }
        hooks.token_count = count;
        hooks.global_token_position = token_position < 0 ? count - 1 : token_position;
        if (hooks.global_token_position >= count) throw std::runtime_error("Token position outside prompt");
        const int layers = llama_model_n_layer(model.get());
        for (int layer : capture_layers) if (layer >= layers) throw std::runtime_error("Capture layer outside trunk");
        if (patch_layer >= layers) throw std::runtime_error("Patch layer outside trunk");
        auto cp = llama_context_default_params();
        cp.n_ctx = std::max(256, count + 32);
        cp.n_batch = count;
        cp.n_ubatch = count;
        cp.n_seq_max = 1;
        cp.n_threads = 4;
        cp.n_threads_batch = 4;
        cp.flash_attn_type = LLAMA_FLASH_ATTN_TYPE_ENABLED;
        cp.no_perf = false;
        const bool callback = enumerate || !capture_layers.empty() || !patch_path.empty();
        if (callback) { cp.cb_eval = evaluate; cp.cb_eval_user_data = &hooks; }
        std::unique_ptr<llama_context, decltype(&llama_free)> ctx(
            llama_init_from_model(model.get(), cp), llama_free);
        if (!ctx) throw std::runtime_error("Context creation failed");
        auto batch = llama_batch_get_one(tokens.data(), count);
        const int status = llama_decode(ctx.get(), batch);
        if (!hooks.error.empty()) throw std::runtime_error(hooks.error);
        if (status != 0) throw std::runtime_error("Forward pass failed: " + std::to_string(status));
        if (hooks.captures.size() != capture_layers.size()) throw std::runtime_error("Requested capture tensor not observed");
        if (!patch_path.empty() && !hooks.patch_applied) throw std::runtime_error("Requested patch tensor not observed");
        const int vocab_size = llama_vocab_n_tokens(vocab);
        const float * raw_logits = llama_get_logits_ith(ctx.get(), -1);
        if (!raw_logits) throw std::runtime_error("No final-position logits");
        std::vector<float> logits(raw_logits, raw_logits + vocab_size);
        write_f32(hooks.out / "logits.f32", logits);
        std::vector<int> indices(vocab_size);
        std::iota(indices.begin(), indices.end(), 0);
        const int top_count = std::min(30, vocab_size);
        std::partial_sort(indices.begin(), indices.begin() + top_count, indices.end(),
                          [&](int a, int b) { return logits[a] > logits[b]; });
        const double maximum = logits[indices.front()];
        double partition = 0;
        for (float logit : logits) partition += std::exp(logit - maximum);
        const double log_partition = maximum + std::log(partition);
        json top = json::array();
        for (int i = 0; i < top_count; ++i) {
            const int token = indices[i];
            top.push_back({{"id", token}, {"piece", token_piece(vocab, token)}, {"logit", logits[token]},
                           {"logprob", logits[token] - log_partition}});
        }
        json tensors = json::array();
        for (const auto & item : hooks.tensors) tensors.push_back(item.second);
        json choice_token_ids = json::object();
        json choice_token_pieces = json::object();
        for (const std::string choice : {"A", "B", " A", " B"}) {
            const int size = -llama_tokenize(vocab, choice.data(), choice.size(), nullptr, 0, false, false);
            if (size <= 0) throw std::runtime_error("Choice tokenization failed");
            std::vector<llama_token> ids(size);
            const int written = llama_tokenize(vocab, choice.data(), choice.size(), ids.data(), ids.size(), false, false);
            if (written <= 0) throw std::runtime_error("Choice tokenization failed");
            ids.resize(written);
            choice_token_ids[choice] = ids;
            choice_token_pieces[choice] = json::array();
            for (llama_token id : ids) choice_token_pieces[choice].push_back(token_piece(vocab, id));
        }
        json metadata = {{"runner_commit", "9d77fa172"}, {"model_path", fs::absolute(model_path).string()},
            {"prompt_path", fs::absolute(prompt_path).string()}, {"prompt_mode", "raw; model special tokens enabled"},
            {"token_ids", tokens}, {"input_token_bytes_hex", input_token_bytes_hex},
            {"vocab_size", vocab_size}, {"trunk_layers", layers},
            {"nextn_layers_metadata", llama_model_n_layer_nextn(model.get())}, {"mtp_loaded", false},
            {"gpu_layers_requested", gpu_layers}, {"context_size", llama_n_ctx(ctx.get())},
            {"batch_size", count}, {"microbatch_size", count}, {"flash_attention", "enabled"},
            {"callback_enabled", callback}, {"captures", hooks.captures}, {"patch_applied", hooks.patch_applied},
            {"patch_file", patch_path}, {"patch_layer", patch_layer},
            {"requested_token_position", token_position < 0 ? json("last") : json(token_position)},
            {"global_token_position", hooks.global_token_position},
            {"patch_physical_row", hooks.patch_applied ? json(hooks.patch_physical_row) : json(nullptr)},
            {"logits_global_token_position", count - 1},
            {"logits_file", "logits.f32"}, {"logits_format", "native little-endian IEEE754 float32; vocabulary token order"},
            {"top_tokens", top}, {"tensors", tensors}, {"choice_token_ids", choice_token_ids},
            {"choice_token_pieces", choice_token_pieces},
            {"choice_tokenization", {{"add_special", false}, {"parse_special", false}}}};
        std::ofstream output(hooks.out / "metadata.json");
        output << metadata.dump(2, ' ', false, json::error_handler_t::replace) << '\n';
        if (!output) throw std::runtime_error("Cannot write metadata");
        llama_perf_context_print(ctx.get());
        std::cout << (fs::absolute(hooks.out) / "metadata.json").string() << '\n';
        return 0;
    } catch (const std::exception & e) {
        std::cerr << "activation_runner: " << e.what() << '\n';
        return 1;
    }
}
