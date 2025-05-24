class Permission:
    def __init__(self, role, path, method):
        self.role = role
        self.path = path
        self.method = method

    def to_dict(self):
        return {
            "role": self.role,
            "path": self.path,
            "method": self.method
        }