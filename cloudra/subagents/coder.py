from cloudra.agent import Follower, load_prompt

class coder(Follower):
    id: str = 'a-6'
    name: str = 'coder'
    type: str = 'follower'
    prompt: str = load_prompt('coder')

    def has_read_permission(self) -> bool:
        return True
    
    def has_write_permission(self) -> bool:
        return True
    
    def script_run_permission(self) -> bool:
        return True
    
    def destructive_permission(self) -> bool:
        return False


def get_class():
    return coder
