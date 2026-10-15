Manuka
======

Nectar cloud user management


See also:
* https://github.com/NeCTAR-RC/manuka-helm
* https://github.com/NeCTAR-RC/puppet-manuka
* https://github.com/NeCTAR-RC/python-manukaclient


Login protocols
---------------

Manuka logs users into the dashboard and creates their keystone account
on first registration. Two login protocols are supported, and a user may
hold an identity from each on the one account (see `external_id.protocol`):

* **Shibboleth (SAML)** at `/login/`. Apache mod_shib authenticates the
  user and manuka reads the attributes from the WSGI environ. The
  `persistent-id` attribute identifies the user.
* **OpenID Connect** at `/oidc/login/`, enabled with the `[oidc]` section
  of `manuka.conf`. Manuka is a confidential client of Keycloak; the `sub`
  claim identifies the user. The claims manuka understands are listed in
  `OIDCAttrMap` in `manuka/views.py` and must be emitted by the provider's
  client mappers.

The first time an OpenID Connect subject is seen manuka looks for an
existing account to attach it to:

1. automatically, when the claims carry a SAML `subject-id` or AAF shared
   token that exactly one existing SAML identity also carries, or an `eppn`
   of an identity that logged in recently (`[oidc]
   eppn_autolink_max_age_days`). Email never links accounts;
2. otherwise the user chooses between linking an existing account, by
   signing in once through Shibboleth at `/login/link/` and confirming both
   identities, and creating a new account.

`manuka-manage oidc-migration-report` shows which active users still need
to link before the Shibboleth login is switched off.


Local development
-----------------

Set `fake_shib = true` to replace mod_shib with a form at `/login/`, and
`[oidc] fake = true` to replace the OpenID Connect provider with a form at
`/oidc/fake/`. Together they let every login and linking flow run in one
browser without an identity federation or Keycloak. Set
`[flask] session_cookie_secure = false` when serving over plain HTTP.
