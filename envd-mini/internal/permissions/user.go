package permissions

import (
	"context"
	"fmt"
	"os/user"
	"strconv"

	"envd-mini/internal/execcontext"
)

func GetUserIds(u *user.User) (uid, gid uint32, err error) {
	newUID, err := strconv.ParseUint(u.Uid, 10, 32)
	if err != nil {
		return 0, 0, fmt.Errorf("error parsing uid '%s': %w", u.Uid, err)
	}

	newGID, err := strconv.ParseUint(u.Gid, 10, 32)
	if err != nil {
		return 0, 0, fmt.Errorf("error parsing gid '%s': %w", u.Gid, err)
	}

	return uint32(newUID), uint32(newGID), nil
}

func GetUser(username string) (u *user.User, err error) {
	u, err = user.Lookup(username)
	if err != nil {
		return nil, fmt.Errorf("error looking up user '%s': %w", username, err)
	}

	return u, nil
}

// GetAuthUser returns the default user (no auth in our system)
func GetAuthUser(ctx context.Context, defaultUser string) (*user.User, error) {
	username, err := execcontext.ResolveDefaultUsername(nil, defaultUser)
	if err != nil {
		return nil, fmt.Errorf("error resolving default user: %w", err)
	}

	return GetUser(username)
}
