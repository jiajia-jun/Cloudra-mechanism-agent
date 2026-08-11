from cloudra.core.agent import Follower


class dft(Follower):
    id: str = 'a-6'
    name: str = 'dft'
    type: str = 'follower'
    prompt_name: str = 'dft'

    def has_read_permission(self) -> bool:
        return True

    def has_write_permission(self) -> bool:
        return True

    def script_run_permission(self) -> bool:
        return True

    def destructive_permission(self) -> bool:
        return True


def get_class():
    return dft
