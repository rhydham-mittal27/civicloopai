# UserService

## Repositories

- `UserRepository`: `get`, `get_by_email`, `add`
- `AuditEventRepository`: planned `add`

## Functions

### `create_user(name, email, role, actor_id=None)`

```text
validate name, email, and role
existing = UserRepository.get_by_email(email)
if existing is not None:
    raise DuplicateUserError
user = User(name=name, email=email, role=role)
UserRepository.add(user)
AuditEventRepository.add(actor_id, "user", user.id, "created", {"role": role})
return user
```

### `get_user(user_id)`

```text
user = UserRepository.get(user_id)
if user is None:
    raise NotFoundError
return user
```

### `get_user_by_email(email)`

```text
return UserRepository.get_by_email(normalize_email(email))
```

### `deactivate_user(user_id, actor_id)`

```text
actor = UserRepository.get(actor_id)
require actor.role == ADMIN
user = UserRepository.get(user_id)
require user is not None
user.is_active = False
AuditEventRepository.add(actor_id, "user", user_id, "deactivated", {})
return user
```

Commit the transaction after the function succeeds.