from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone


class Article(models.Model):
    """博客文章模型"""
    title = models.CharField(max_length=200, verbose_name='标题')
    slug = models.SlugField(max_length=200, unique=True, verbose_name='URL别名')
    author = models.ForeignKey(User, on_delete=models.CASCADE, verbose_name='作者')
    content = models.TextField(verbose_name='内容')
    excerpt = models.TextField(max_length=500, blank=True, verbose_name='摘要')
    cover_image = models.URLField(max_length=500, blank=True, verbose_name='封面图片URL')
    category = models.CharField(max_length=50, default='未分类', verbose_name='分类')
    tags = models.CharField(max_length=200, blank=True, verbose_name='标签（逗号分隔）')
    views = models.IntegerField(default=0, verbose_name='浏览量')
    is_published = models.BooleanField(default=True, verbose_name='是否发布')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='更新时间')
    published_at = models.DateTimeField(default=timezone.now, verbose_name='发布时间')

    class Meta:
        verbose_name = '文章'
        verbose_name_plural = '文章'
        ordering = ['-published_at', '-created_at']

    def __str__(self):
        return self.title

    def get_tags_list(self):
        """获取标签列表"""
        if self.tags:
            return [tag.strip() for tag in self.tags.split(',') if tag.strip()]
        return []

