from cloudra.core.agent import Follower


class md(Follower):
    id: str = 'a-5'
    name: str = 'md'
    type: str = 'follower'
    prompt_name: str = 'md'

    def has_read_permission(self) -> bool:
        return True

    def has_write_permission(self) -> bool:
        return True

    def script_run_permission(self) -> bool:
        return True

    def destructive_permission(self) -> bool:
        return True


def get_class():
    return md
