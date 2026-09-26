import hashlib
import os

import frontmatter as frt

# 模块级缓存按 SKILL.md 内容 revision 失效。Phase 6 后 skill manifest
# 允许在进程运行期间更新，不能再假设目录在整个进程生命周期中静态不变。
_SKILL_DATAS_CACHE: dict[str, tuple[str, list[dict]]] = {}

# NOTE: Skills 模型仅作为 skill frontmatter 的字段参照，当前未被实例化使用。
# 若后续需要校验 skill 元数据，可取消注释并补全默认值。
# class Skills(BaseModel):
#     name: str
#     description: str
#     path: str
#     scripts: list = []
#     references: list = []


class skill_loader:

    # Skills are bundled with the package, not user data（base/ 上溯一级到包根）
    base_path: str = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'skills'
    )

    def __init__(self):
        # FIX: 原代码直接用了模块级变量 base_path（缺少 self.），在实例方法中访问类属性应加 self
        self.namelst = os.listdir(self.base_path)

        self.pathlst = [os.path.join(self.base_path, skill_name) for skill_name in self.namelst]

        self.md_pathlst = [os.path.join(path,'SKILL.md') for path in self.pathlst if os.path.isdir(path)]

    def skill_datas_get(self) -> list[dict]:
        revision_hash = hashlib.sha256()
        for md in sorted(self.md_pathlst):
            revision_hash.update(md.encode("utf-8"))
            try:
                with open(md, "rb") as stream:
                    revision_hash.update(stream.read())
            except OSError:
                continue
        revision = revision_hash.hexdigest()
        cached = _SKILL_DATAS_CACHE.get(self.base_path)
        if cached is None or cached[0] != revision:
            mds = self.md_pathlst
            datas = []
            for md in mds:
                with open(md, 'r', encoding='utf-8') as f:
                    post = frt.load(f)
                    metadata = post.metadata
                    content = post.content

                    # FIX: dict.update() 返回 None，原代码把 None 当数据 append 了
                    # 这里直接修改 metadata dict 后 append（frontmatter 的 metadata 是普通 dict）
                    metadata['content'] = content
                    datas.append(metadata)

            _SKILL_DATAS_CACHE[self.base_path] = (revision, datas)

        return _SKILL_DATAS_CACHE[self.base_path][1]

    def list_skills(self) -> list[dict]:
        """Return list of all available skills with name and description."""
        datas = self.skill_datas_get()
        return [{"name": d.get("name", ""), "description": d.get("description", "")} for d in datas if d.get("name")]

    def list_references(self, skill_name: str) -> list[str]:
        """Return relative paths of all available reference files for a given skill."""
        possible_dirs = ['references', 'reference', 'ref']
        refs = []
        for dir_name in possible_dirs:
            dir_path = os.path.join(self.base_path, skill_name, dir_name)
            if os.path.isdir(dir_path):
                for root, _, files in os.walk(dir_path):
                    for file in sorted(files):
                        if not file.startswith('.'):
                            rel = os.path.relpath(os.path.join(root, file), dir_path)
                            refs.append(rel)
        return sorted(refs)

    def get_reference(self, skill_name, ref_name) -> str:
        # 支持多种可能的资料文件夹命名约定
        possible_dirs = ['references', 'reference', 'ref']

        for dir_name in possible_dirs:
            ref_path = os.path.join(self.base_path, skill_name, dir_name, ref_name)
            if os.path.isfile(ref_path):
                with open(ref_path, 'r', encoding='utf-8') as f:
                    return f.read()
            elif os.path.isdir(ref_path):
                dir_filelst = sorted(os.listdir(ref_path))
                return f"Reference '{ref_name}' is a directory containing: {dir_filelst}. Please specify {ref_name}/<filename>."

        return 'Reference not found.'

    # FIX: 原拼写为 skill_dsatas_get（多打了个 s）
    def get_content(self, skill_name) -> str:
        datas = self.skill_datas_get()
        for data in datas:
            if data['name'] == skill_name:
                return data['content']
        return 'skill does not exist.'














