from cloudra.core.agent import Follower


class researcher(Follower):
    id: str = 'a-3'
    name: str = 'researcher'
    type: str = 'follower'
    prompt_name: str = 'researcher'

    def has_read_permission(self) -> bool:
        return True

    def has_write_permission(self) -> bool:
        return True

    def script_run_permission(self) -> bool:
        return True

    def destructive_permission(self) -> bool:
        return True


def get_class():
    return researcher
