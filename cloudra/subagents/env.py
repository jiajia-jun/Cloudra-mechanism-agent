from cloudra.agent import Follower


class env(Follower):
    id: str = 'a-8'
    name: str = 'env'
    type: str = 'follower'
    prompt_name: str = 'env'

    def has_read_permission(self) -> bool:
        return True

    def has_write_permission(self) -> bool:
        return True

    def script_run_permission(self) -> bool:
        return True

    def destructive_permission(self) -> bool:
        return True


def get_class():
    return env
