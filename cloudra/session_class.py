import os

from datetime import datetime

class Session:
    id: str
    path: str
    create_time: datetime
    state: str = 'sleeping'
    tool_calling: dict = {}
    def __init__(self, id: str, path: str) -> None:
        self.create_time = datetime.now()
        self.id = id
        self.path = path
        self.state = 'sleeping'
        session_dict = self.to_json()
        import json
        with open(self.path, 'w', encoding='utf-8') as f:
            json.dump(session_dict, f, ensure_ascii=False, indent=4)
        

    def to_json(self) -> dict:
        create_time = self.create_time
        if isinstance(create_time, datetime):
            create_time = create_time.isoformat()
        json_dict = {
            'id': self.id,
            'path': self.path,
            'create_time': create_time,
            'state': self.state,
            'tool_calling': self.tool_calling
        }
        return json_dict
    
    def upload_json(self):
        import json
        with open(self.path, 'w', encoding='utf-8') as f:
            json.dump(self.to_json(), f, ensure_ascii=False, indent=4)

    


