from cloudra.agent import Follower, load_prompt

class operator(Follower):
    id: str = 'a-5'
    name: str = 'operator'
    type: str = 'follower'
    prompt: str = load_prompt('operator')

    def has_read_permission(self) -> bool:
        return True
    
    def has_write_permission(self) -> bool:
        return True
    
    def script_run_permission(self) -> bool:
        return True
    
    def destructive_permission(self) -> bool:
        return True


def get_class():
    return operator
