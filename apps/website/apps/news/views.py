from django.shortcuts import render, get_object_or_404
from django.core.paginator import Paginator
from django.db.models import Q
from .models import Article


def news_list(request):
    """资讯列表页"""
    articles = Article.objects.filter(is_published=True)
    
    # 搜索功能
    search_query = request.GET.get('search', '')
    if search_query:
        articles = articles.filter(
            Q(title__icontains=search_query) |
            Q(content__icontains=search_query) |
            Q(excerpt__icontains=search_query)
        )
    
    # 分类筛选
    category = request.GET.get('category', '')
    if category:
        articles = articles.filter(category=category)
    
    # 标签筛选
    tag = request.GET.get('tag', '')
    if tag:
        articles = articles.filter(tags__icontains=tag)
    
    # 分页
    paginator = Paginator(articles, 9)  # 每页9篇文章
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    # 获取所有分类和标签（用于筛选）
    categories = Article.objects.filter(is_published=True).values_list('category', flat=True).distinct()
    all_tags = []
    for article in Article.objects.filter(is_published=True):
        all_tags.extend(article.get_tags_list())
    unique_tags = sorted(list(set(all_tags)))
    
    context = {
        'page_obj': page_obj,
        'articles': page_obj,
        'categories': categories,
        'tags': unique_tags,
        'search_query': search_query,
        'current_category': category,
        'current_tag': tag,
    }
    
    return render(request, 'news/list.html', context)


def article_detail(request, slug):
    """文章详情页"""
    article = get_object_or_404(Article, slug=slug, is_published=True)
    
    # 增加浏览量
    article.views += 1
    article.save(update_fields=['views'])
    
    # 获取相关文章（同分类的其他文章）
    related_articles = Article.objects.filter(
        category=article.category,
        is_published=True
    ).exclude(id=article.id)[:3]
    
    # 获取上一篇文章和下一篇文章
    prev_article = Article.objects.filter(
        is_published=True,
        published_at__lt=article.published_at
    ).order_by('-published_at').first()
    
    next_article = Article.objects.filter(
        is_published=True,
        published_at__gt=article.published_at
    ).order_by('published_at').first()
    
    context = {
        'article': article,
        'related_articles': related_articles,
        'prev_article': prev_article,
        'next_article': next_article,
    }
    
    return render(request, 'news/detail.html', context)

