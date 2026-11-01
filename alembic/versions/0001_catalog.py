"""Persist the catalog and visitor-scoped bookmarks."""
from alembic import op
import sqlalchemy as sa

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("courses",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=False),
        sa.Column("title", sa.String(1000), nullable=False),
        sa.Column("instructor", sa.String(500), nullable=False),
        sa.Column("image_url", sa.Text, nullable=False),
        sa.Column("blob_path", sa.String(500)),
        sa.Column("total_hour", sa.Float),
        sa.Column("description", sa.Text, nullable=False),
        sa.Column("slug", sa.String(1000), nullable=False),
        sa.Column("slug_part", sa.String(500), nullable=False),
        sa.Column("rate", sa.Float),
        sa.Column("category", sa.String(200), nullable=False),
        sa.Column("badge", sa.String(100)),
        sa.Column("language", sa.String(100)),
        sa.Column("created_at", sa.DateTime, nullable=False),
        sa.Column("is_expired", sa.Boolean, nullable=False),
        sa.Column("total_practice_test", sa.Integer, nullable=False),
        sa.Column("total_practice_test_questions", sa.Integer, nullable=False),
        sa.Column("is_practice_test", sa.Boolean, nullable=False),
        sa.Column("enroll_url", sa.Text),
        sa.Column("coupon_code", sa.String(500)),
        sa.Column("moreinfo", sa.Text),
        sa.Column("total_section", sa.Integer),
        sa.Column("udemy_id", sa.String(100)),
        sa.Column("learn_who", sa.JSON),
        sa.Column("for_who", sa.JSON),
        sa.Column("requirements", sa.JSON),
        sa.Column("detail_fetched_at", sa.DateTime),
        sa.Column("updated_at", sa.DateTime, nullable=False),
    )
    for name in ("slug", "slug_part", "category", "created_at"):
        op.create_index(f"ix_courses_{name}", "courses", [name], unique=name == "slug")
    op.create_table("saved_courses",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("visitor_id", sa.String(64), nullable=False),
        sa.Column("course_id", sa.Integer, sa.ForeignKey("courses.id", ondelete="CASCADE"), nullable=False),
        sa.Column("created_at", sa.DateTime, nullable=False),
        sa.UniqueConstraint("visitor_id", "course_id", name="uq_saved_visitor_course"),
    )
    op.create_index("ix_saved_courses_visitor_id", "saved_courses", ["visitor_id"])
    op.create_index("ix_saved_courses_course_id", "saved_courses", ["course_id"])
    op.create_table("catalog_meta",
        sa.Column("key", sa.String(200), primary_key=True),
        sa.Column("value", sa.Text, nullable=False),
        sa.Column("updated_at", sa.DateTime, nullable=False),
    )


def downgrade():
    op.drop_table("saved_courses")
    op.drop_table("catalog_meta")
    op.drop_table("courses")
