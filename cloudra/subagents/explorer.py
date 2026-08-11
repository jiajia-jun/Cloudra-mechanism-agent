from cloudra.core.agent import Follower


class explorer(Follower):
    id: str = 'a-1'
    name: str = 'explorer'
    type: str = 'follower'
    prompt_name: str = 'explorer'

    def has_read_permission(self) -> bool:
        return True

    def has_write_permission(self) -> bool:
        return False

    def script_run_permission(self) -> bool:
        return False

    def destructive_permission(self) -> bool:
        return False


def get_class():
    return explorer
