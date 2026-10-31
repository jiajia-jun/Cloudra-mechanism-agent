#!/usr/bin/env bash
set -euo pipefail

# Sources, libraries and executable stay outside the repository.
repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
research_dir=/private/tmp/cloudra-model-interpretability
source_dir="$research_dir/llama.cpp"
build_dir="$source_dir/build-activation"
revision=9d77fa172
if [[ ! -d "$source_dir/.git" ]]; then
    mkdir -p "$research_dir"
    git clone --filter=blob:none --no-checkout https://github.com/ggml-org/llama.cpp.git "$source_dir"
    git -C "$source_dir" checkout "$revision"
fi
if [[ "$(git -C "$source_dir" rev-parse --short=9 HEAD)" != "$revision" ]]; then
    printf 'Expected llama.cpp %s in %s\n' "$revision" "$source_dir" >&2
    exit 1
fi
cmake -S "$source_dir" -B "$build_dir" -G Ninja \
    -DCMAKE_BUILD_TYPE=Release -DBUILD_SHARED_LIBS=ON \
    -DLLAMA_BUILD_COMMON=OFF -DLLAMA_BUILD_TESTS=OFF \
    -DLLAMA_BUILD_TOOLS=OFF -DLLAMA_BUILD_EXAMPLES=OFF \
    -DLLAMA_BUILD_SERVER=OFF -DLLAMA_BUILD_APP=OFF -DLLAMA_BUILD_UI=OFF \
    -DLLAMA_OPENSSL=OFF -DGGML_METAL=ON -DGGML_METAL_EMBED_LIBRARY=ON
cmake --build "$build_dir" --target llama --parallel 4
clang++ -std=c++17 -O2 -Wall -Wextra \
    -I"$source_dir/include" -I"$source_dir/ggml/include" -I"$source_dir/vendor/nlohmann" \
    "$repo_root/scripts/model_semantics/activation_runner.cpp" \
    -L"$build_dir/bin" -Wl,-rpath,"$build_dir/bin" \
    -lllama -lggml -lggml-base -o "$research_dir/activation_runner"
printf 'Built %s\n' "$research_dir/activation_runner"
