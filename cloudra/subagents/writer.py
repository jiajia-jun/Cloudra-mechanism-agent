from cloudra.agent import Follower


class writer(Follower):
    id: str = 'a-2'
    name: str = 'writer'
    type: str = 'follower'
    prompt_name: str = 'writer'

    def has_read_permission(self) -> bool:
        return True

    def has_write_permission(self) -> bool:
        return True

    def script_run_permission(self) -> bool:
        return False

    def destructive_permission(self) -> bool:
        return False


def get_class():
    return writer
