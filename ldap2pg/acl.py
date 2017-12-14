from .psql import Query
from .utils import AllDatabases, UserError, unicode


class Acl(object):
    TYPES = {}
    itemfmt = "%(dbname)s.%(schema)s for %(owner)s"

    def __init__(self, name, inspect=None, grant=None, revoke=None):
        self.name = name
        self.inspect = inspect
        self.grant_sql = grant
        self.revoke_sql = revoke

    def __eq__(self, other):
        return unicode(self) == unicode(other)

    def __lt__(self, other):
        return unicode(self) < unicode(other)

    def __repr__(self):
        return '<%s %s>' % (self.__class__.__name__, self)

    def __str__(self):
        return self.name

    @classmethod
    def factory(cls, name, **kw):
        implcls = cls.TYPES[kw.pop('type')]
        return implcls(name, **kw)

    @classmethod
    def register(cls, subclass):
        cls.TYPES[subclass.__name__.lower()] = subclass
        return subclass

    def grant(self, item):
        fmt = "Grant %(acl)s on " + self.itemfmt + " to %(role)s."
        return Query(
            fmt % item.__dict__,
            item.dbname,
            self.grant_sql.format(
                database='"%s"' % item.dbname,
                schema='"%s"' % item.schema,
                owner='"%s"' % item.owner,
                role='"%s"' % item.role,
            ),
        )

    def revoke(self, item):
        fmt = "Revoke %(acl)s on " + self.itemfmt + " from %(role)s."
        return Query(
            fmt % item.__dict__,
            item.dbname,
            self.revoke_sql.format(
                database='"%s"' % item.dbname,
                schema='"%s"' % item.schema,
                owner='"%s"' % item.owner,
                role='"%s"' % item.role,
            ),
        )


@Acl.register
class DatAcl(Acl):
    itemfmt = '%(dbname)s'

    def expanddb(self, item, databases):
        if item.dbname is AclItem.ALL_DATABASES:
            dbnames = databases.keys()
        else:
            dbnames = [item.dbname]

        for dbname in dbnames:
            yield item.copy(acl=self.name, dbname=dbname)

    def expand(self, item, databases, owners):
        for exp in self.expanddb(item, databases):
            yield exp


@Acl.register
class NspAcl(DatAcl):
    itemfmt = '%(dbname)s.%(schema)s'

    def expandschema(self, item, databases):
        if item.schema is AclItem.ALL_SCHEMAS:
            try:
                schemas = databases[item.dbname]
            except KeyError:
                fmt = "Database %s does not exists or is not managed."
                raise UserError(fmt % (item.dbname))
        else:
            schemas = [item.schema]
        for schema in schemas:
            yield item.copy(acl=self.name, schema=schema)

    def expand(self, item, databases, owners):
        for datexp in super(NspAcl, self).expand(item, databases, owners):
            for nspexp in self.expandschema(datexp, databases):
                yield nspexp


@Acl.register
class DefAcl(NspAcl):
    itemfmt = '%(dbname)s.%(schema)s for %(owner)s'

    def expand(self, item, databases, owners):
        for expand in super(DefAcl, self).expand(item, databases, []):
            for owner in owners:
                yield expand.copy(owner=owner)


class AclItem(object):
    ALL_DATABASES = AllDatabases()
    ALL_SCHEMAS = None

    @classmethod
    def from_row(cls, *args):
        return cls(*args)

    def __init__(self, acl, dbname=None, schema=None, role=None, full=True,
                 owner=None):
        self.acl = acl
        self.dbname = dbname
        self.schema = schema
        self.role = role
        self.full = full
        self.owner = owner

    def __lt__(self, other):
        return self.as_tuple() < other.as_tuple()

    def __str__(self):
        full_map = {None: 'n/a', True: 'granted', False: 'incomplete'}
        fmt = (
            '%(acl)s on %(dbname)s.%(schema)s for %(owner)s'
            ' to %(role)s (%(full)s)'
        )
        return fmt % dict(
            self.__dict__,
            schema=self.schema or '*',
            owner=self.owner or '*',
            full=full_map[self.full],
        )

    def __repr__(self):
        return '<%s %s>' % (self.__class__.__name__, self)

    def __hash__(self):
        return hash(self.as_tuple())

    def __eq__(self, other):
        return self.as_tuple() == other.as_tuple()

    def as_tuple(self):
        return (self.acl, self.dbname, self.schema, self.role, self.owner)

    def copy(self, **kw):
        return self.__class__(**dict(dict(
            acl=self.acl,
            role=self.role,
            dbname=self.dbname,
            schema=self.schema,
            full=self.full,
            owner=self.owner,
        ), **kw))


class AclSet(set):
    def expanditems(self, aliases, acl_dict, databases, owners):
        for item in self:
            for aclname in aliases[item.acl]:
                acl = acl_dict[aclname]
                for expansion in acl.expand(item, databases, owners):
                    yield expansion
