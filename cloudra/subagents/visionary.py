from cloudra.agent import Follower, load_prompt


class visionary(Follower):
    id: str = 'a-4'
    name: str = 'visionary'
    type: str = 'follower'
    prompt: str = load_prompt('visionary')

    def has_read_permission(self) -> bool:
        return True

    def has_write_permission(self) -> bool:
        return False

    def script_run_permission(self) -> bool:
        return False

    def destructive_permission(self) -> bool:
        return False


def get_class():
    return visionary
