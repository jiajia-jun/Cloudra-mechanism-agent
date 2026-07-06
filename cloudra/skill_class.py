from pydantic import BaseModel  # FIX: 原拼写为 Basemodel，Pydantic v2 正确名为 BaseModel
import os
import frontmatter as frt

# NOTE: Skills 模型仅作为 skill frontmatter 的字段参照，当前未被实例化使用。
# 若后续需要校验 skill 元数据，可取消注释并补全默认值。
# class Skills(BaseModel):
#     name: str
#     description: str
#     path: str
#     scripts: list = []
#     references: list = []


class skill_loader:

    # Skills are bundled with the package, not user data
    base_path: str = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'skills')

    def __init__(self):
        # FIX: 原代码直接用了模块级变量 base_path（缺少 self.），在实例方法中访问类属性应加 self
        self.namelst = os.listdir(self.base_path)

        self.pathlst = [os.path.join(self.base_path, skill_name) for skill_name in self.namelst]

        self.md_pathlst = [os.path.join(path,'SKILL.md') for path in self.pathlst if os.path.isdir(path)]

    def skill_datas_get(self) -> list[dict]:
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

        return datas

    def get_reference(self, skill_name, ref_name) -> str:
        # 支持多种可能的资料文件夹命名约定
        possible_dirs = ['references', 'reference', 'ref']
        
        for dir_name in possible_dirs:
            ref_path = os.path.join(self.base_path, skill_name, dir_name, ref_name)
            if os.path.isfile(ref_path):
                with open(ref_path, 'r', encoding='utf-8') as f:
                    return f.read()
            elif os.path.isdir(ref_path):
                dir_filelst = os.listdir(ref_path)
                return fr'该reference为文件夹，文件夹下有：{dir_filelst} ,请根据需要输入 {ref_name}/filename 调用资料，win系统请用 {ref_name}\filename'

        return '该资料不存在。'

    # FIX: 原拼写为 skill_dsatas_get（多打了个 s）
    def get_content(self, skill_name) -> str:
        datas = self.skill_datas_get()
        for data in datas:
            if data['name'] == skill_name:
                return data['content']
        return 'skill不存在。'
















