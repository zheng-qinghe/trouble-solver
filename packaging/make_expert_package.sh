#!/usr/bin/env bash
# 从本仓库**重建** WorkBuddy 专家包。
#
# 设计要点：**仓库是唯一真源，专家包是产物**。
# 引擎（src/）、四阶段指令（prompts/）、真实案例（examples/）都在构建时拷贝，
# 所以仓库一改，重跑本脚本就同步了 —— 不存在"两份拷贝互相漂移"。
#
#   bash packaging/make_expert_package.sh [输出目录]
#   默认： $WORKBUDDY_CONFIG_DIR/plugins/marketplaces/my-experts/plugins/troublesolver
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PY="${TSOLVE_PYTHON:-python3}"
CFG="${WORKBUDDY_CONFIG_DIR:-$HOME/.workbuddy}"
DEST="${1:-$CFG/plugins/marketplaces/my-experts/plugins/troublesolver}"
DEF="$REPO/packaging/expert"

echo "repo : $REPO"
echo "dest : $DEST"

# 1) 骨架
mkdir -p "$DEST/.codebuddy-plugin" "$DEST/agents" "$DEST/bin" "$DEST/avatars" \
         "$DEST/skills/troublesolver/scripts/troublesolver" \
         "$DEST/skills/troublesolver/prompts" \
         "$DEST/skills/troublesolver/references" \
         "$DEST/skills/troublesolver/examples"

# 2) 定义源（人手维护，就在本仓库里）
cp "$DEF/plugin.json"                                  "$DEST/.codebuddy-plugin/plugin.json"
cp "$DEF"/agents/*.md                                  "$DEST/agents/"
cp "$DEF"/bin/*                                        "$DEST/bin/"
chmod +x "$DEST"/bin/*
[ -f "$DEF/README.md" ] && cp "$DEF/README.md"         "$DEST/README.md"
[ -f "$DEF/avatars/expert.png" ] && cp "$DEF/avatars/expert.png" "$DEST/avatars/expert.png"
cp "$DEF/skills/troublesolver/SKILL.md"                "$DEST/skills/troublesolver/SKILL.md"
cp "$DEF"/skills/troublesolver/references/*.md         "$DEST/skills/troublesolver/references/"
cp "$DEF"/skills/troublesolver/scripts/*.py            "$DEST/skills/troublesolver/scripts/"

# 3) 引擎 / 指令 / 案例 —— 构建时从仓库拷贝，杜绝漂移
cp "$REPO"/src/troublesolver/*.py                      "$DEST/skills/troublesolver/scripts/troublesolver/"
cp "$REPO"/prompts/*.md                                "$DEST/skills/troublesolver/prompts/"
"$PY" - "$REPO/examples" "$DEST/skills/troublesolver/examples" <<'PY'
import shutil, sys
shutil.copytree(sys.argv[1], sys.argv[2], dirs_exist_ok=True,
                ignore=shutil.ignore_patterns("out", "__pycache__", "*.pyc"))
print("  已同步 examples/")
PY

# 4) 清缓存（跑过一次就会生成 __pycache__，不能进包）
find "$DEST" -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null || true
find "$DEST" -name "*.pyc" -delete 2>/dev/null || true

# 5) 校验 + 注册。
#    校验器强制"必须装在专家目录下"，所以 DEST 不在官方位置时只生成文件、不校验
#    （例如构建到 /tmp 做对比）。这样脚本既能当"同步工具"，也能当"产线"。
EXPERT_ROOT="$CFG/plugins/marketplaces/my-experts/plugins"
case "$DEST" in
  "$EXPERT_ROOT"/*) ;;
  *) echo "（DEST 不在专家目录 $EXPERT_ROOT 下 → 只生成文件，跳过校验/注册）"
     echo "✅ 已生成：$DEST"; exit 0 ;;
esac

EM=""
for cand in $(ls -d "$CFG"/plugins/cache/*/expert-manager/*/ 2>/dev/null) \
            "$(ls -d /Applications/WorkBuddy.app/Contents/Resources/app.asar.unpacked/resources/plugins/*/skills/expert-manager 2>/dev/null)"; do
  if [ -f "$cand/scripts/validate_expert.py" ]; then EM="$cand"; break; fi
done
if [ -n "$EM" ]; then
  "$PY" "$EM/scripts/validate_expert.py" "$DEST"
  "$PY" "$EM/scripts/register_expert.py" "$DEST" || true
else
  echo "（未找到 expert-manager 脚本，跳过校验/注册；专家包文件已生成）"
fi
echo "✅ 专家包已重建：$DEST"
