#coding=utf-8
from __future__ import unicode_literals
import sys
reload(sys)
sys.setdefaultencoding( "utf-8" )

try:
    from urllib import quote_plus #python 2
except:
    pass

from django.shortcuts import render,get_object_or_404,redirect
from django.http import HttpResponse,HttpResponseRedirect,HttpResponseBadRequest

from posts.models import  Category,Post,Comment,TaggedItem
from posts.forms import PostForm,CommentForm,TaggedItemForm

from django.contrib import messages
from django.core import serializers
from django.views.generic import RedirectView

from uuslug import slugify
#Paginator
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
#search
from django.db.models import Q,Count
#comments
from django.contrib.contenttypes.models import ContentType
#actions
from actions.utils import create_action


import redis
from django.conf import settings
r = redis.StrictRedis(host=settings.REDIS_HOST,
                      port=settings.REDIS_PORT,
                      db=settings.REDIS_DB)


def index(request):
    templates='post/index.html'
    # queryset = Post.get_published()
    queryset = Post.objects.all()

    query = request.GET.get("q")
    if query:
		queryset = queryset.filter(
				Q(title__icontains=query)|
				Q(content__icontains=query)|
				Q(user__first_name__icontains=query) |
				Q(user__last_name__icontains=query)
				).distinct()


    paginator = Paginator(queryset, 3) # Show 25 contacts per page
    page_request_var = "page"
    page = request.GET.get(page_request_var)
    try:
        queryset = paginator.page(page)
    except PageNotAnInteger:
        # If page is not an integer, deliver first page.
        queryset = paginator.page(1)
    except EmptyPage:
        if request.is_ajax():
            # If the request is AJAX and the page is out of range return an empty page
            return HttpResponse('')
        # If page is out of range (e.g. 9999), deliver last page of results.
        queryset = paginator.page(paginator.num_pages)

    context = {
        "title": "Index",
        "object_list" : queryset,
        "page_request_var":page_request_var,
    }
    if request.is_ajax():
        return render(request,'post/list_ajax.html',context)

    return render(request,templates,context)

def detail(request,slug=None):
    templates='post/detail.html'
    instance = get_object_or_404(Post,slug=slug)
    if instance.status == 'D':
        if not request.user.is_staff or not request.user.is_superuser:
            raise Http404
    # share_string = quote_plus(instance.content)
    share_string = instance.content
    # content_type = ContentType.objects.get_for_model(Post)
    # obj_id = instance.id
    # comments = Comment.objects.filter(content_type=content_type,object_id=obj_id)
    # comments = Comment.objects.filter_by_instance(instance)
    # comments = instance.comments
    initial_data = {
			"content_type": instance.get_content_type,
			"object_id": instance.id
	}
    form = CommentForm(request.POST or None, initial=initial_data)
    if form.is_valid():
        c_type = form.cleaned_data.get("content_type")
        content_type = ContentType.objects.get(model=c_type)
        obj_id = form.cleaned_data.get('object_id')
        content_data = form.cleaned_data.get("content")

        parent_obj = None
        try:
            parent_id = int(request.POST.get("parent_id"))
        except:
            parent_id = None

        if parent_id:
            parent_qs = Comment.objects.filter(id=parent_id)
            if parent_qs.exists() and parent_qs.count() == 1:
                parent_obj = parent_qs.first()


        new_comment, created = Comment.objects.get_or_create(
                            user = request.user,
                            content_type= content_type,
                            object_id = obj_id,
                            content = content_data,
                            parent = parent_obj,
                        )
        create_action(request.user, 'create comment', instance)
        if created:
            # create_action(request.user, 'create comment', content_data)

            print("it worked!")
        #清楚评论框里的内容
        return HttpResponseRedirect(new_comment.content_object.get_absolute_url())


    # increment total post views by 1
    total_views = r.incr('post:{}:views'.format(instance.id))
    # increment post ranking by 1
    r.zincrby('post_ranking', instance.id, 1)

    comments = instance.comments
    comments_count = instance.comments.count()
    tags=instance.tags
    context = {
        "title": instance.title,
        "instance": instance,
        # "tag": tag,
        "share_string": share_string,
        "comments": comments,
        "comment_form":form,
        "comments_count":comments_count,
        "tags":tags,
        'total_views': total_views,
    }

    return render(request,templates,context)

def create(request):
    templates='post/form.html'
    post_form = PostForm(request.POST or None,request.FILES or None)
    tag_form = TaggedItemForm(request.POST or None)
    # b = Post.objects.get()
    if all([post_form.is_valid(),tag_form.is_valid()]):
        instance=post_form.save(commit=False)
        instance.save()
        create_action(request.user, 'create post', instance)

        content_type = ContentType.objects.get(model=instance.get_content_type)
        tag = None
        try:
            tag = tag_form.cleaned_data.get("tag")

        except:
            tag = None

        if tag:
            tag_qs = TaggedItem.objects.filter(tag=tag)
            if tag_qs.exists() and tag_qs.count() >= 1:
                tag = tag_qs.first()

            try:
                tags_list = tag.split(',')
            except:
                tags_list = str(tag).split(',')

            for tag in tags_list:
                whitespace = tag.strip()
                slug = "%s" %(whitespace.replace(" ", "-"))
                tag_slug=slugify(slug)

                tag_slug_qs = TaggedItem.objects.filter(tag_slug=slugify(slug)).values('tag_slug')
                if tag_slug_qs.exists() and tag_slug_qs.count() >= 1:
                    slug_qs= tag_slug_qs.first()
                    tag_slug=slug_qs['tag_slug']

                print 'create',request.user,instance.get_content_type,instance.id,tag
                new_tag, created = TaggedItem.objects.get_or_create(
                                    user = request.user,
                                    content_type= content_type,
                                    object_id = instance.id,
                                    tag = tag,
                                    tag_slug = tag_slug,
                                )

        return HttpResponseRedirect(instance.get_absolute_url())

    context ={
        "form":post_form,
        "tag_form":tag_form,
    }
    return render(request,templates,context)

def update(request,slug=None):
    templates='post/form.html'
    instance = get_object_or_404(Post,slug=slug)
    print 'instance',instance,instance.id,instance.tags.values('id')
    post_form = PostForm(request.POST or None,request.FILES or None, instance=instance)

    queryset_tag = None

    try:
        q=instance.tags.values('id')
        l = []
        for item in q:
            l.append(item['id'])

        # topic_slug= TaggedItem.objects.filter(tag_slug__contains=topic).values('object_id')
        # queryset=Post.objects.filter(id__in=topic_slug)
        # queryset_tags=TaggedItem.objects.filter(object_id=int(instance.id)).values('tag').order_by('tag')
        queryset_tags=TaggedItem.objects.filter(object_id=int(instance.id)).values('tag').order_by('tag')

        # for tag in queryset_tag:
        #     print tag
        # queryset_tags=TaggedItem.objects.get(object_id=instance.id)
        # print queryset_tags
        # queryset_tag = [item for item in TaggedItem.objects.filter(object_id=int(instance.id)).values('tag')]
        current_list = []
        for obj in queryset_tags:
            for k,v in  obj.items():
                current_list.append(v.encode('utf8'))

        return_current_list = ','.join(current_list)
        print 'current_list',current_list,type(current_list)
        queryset_tag= return_current_list.encode('utf8')

        # if len(queryset_tag) == 1:
        #     obj = queryset_tag[0]
        #     print obj
        # else:
        #     pass

    except:
        queryset_tag = None
        current_list = []

    initial_data = {
			"content_type": instance.get_content_type,
			"object_id": instance.id,
            "tag": queryset_tag,
	}

    tag_form = TaggedItemForm(request.POST or None, initial=initial_data)

    print 'current_list',current_list
    if all([post_form.is_valid(),tag_form.is_valid()]):
        instance=post_form.save(commit=False)
        instance.save()
        create_action(request.user, 'update posts', instance)

        content_type = ContentType.objects.get(model=instance.get_content_type)

        tag = None
        try:
            # tag = request.POST.get("tag")
            tag = tag_form.cleaned_data.get("tag")


        except:
            tag = None

        n=[]
        if tag:
            tag_qs = TaggedItem.objects.filter(tag=tag)
            if tag_qs.exists() and tag_qs.count() >= 1:
                tag = tag_qs.first()
            print 'tags_list',tag,type(tag)

            try:
                tags_list = tag.split(',')
            except:
                tags_list = str(tag).split(',')

            for tag in tags_list:
                whitespace = tag.strip()
                slug = "%s" %(whitespace.replace(" ", "-"))
                tag_slug=slugify(slug)

                tag_slug_qs = TaggedItem.objects.filter(tag_slug=slugify(slug)).values('tag_slug')
                if tag_slug_qs.exists() and tag_slug_qs.count() >= 1:
                    slug_qs= tag_slug_qs.first()
                    tag_slug=slug_qs['tag_slug']


                print 'create',request.user,instance.get_content_type,instance.id,tag
                new_tag, created = TaggedItem.objects.get_or_create(
                                    user = request.user,
                                    content_type= content_type,
                                    object_id = instance.id,
                                    tag = tag,
                                    tag_slug = tag_slug,
                                )

                tqs = TaggedItem.objects.filter(tag=tag).values('id')
                for item in tqs:
                    n.append(item['id'])

        m=[]
        for it in  l:
            if it not in n:
               m.append(it)

        for id in m:
            new_tag= TaggedItem.objects.filter(id=id).delete()
            print new_tag


        return HttpResponseRedirect(instance.get_absolute_url())

    context ={
        "title":instance.title,
        "instance":instance,
        "form":post_form,
        "tag_form":tag_form,
    }
    return render(request,templates,context)

def delete(request,id=None):
    instance = get_object_or_404(Post,id=id)
    instance.delete()
    return redirect("posts:post-index")

def comment_delete(request, id):
    # obj = get_object_or_404(Comment, id=id)
    obj=Comment.objects.get(id=id)
    try:
        obj=Comment.objects.get(id=id)
    except:
        raise Http404

    if obj.user != request.user:
        #messages.success(request, "You do not have permission to view this.")
        #raise Http404
        reponse = HttpResponse("You do not have permission to do this.")
        reponse.status_code = 403
        return reponse
        #return render(request, "confirm_delete.html", context, status_code=403)

    if request.method == "POST":
        parent_obj_url = obj.content_object.get_absolute_url()
        obj.delete()
        messages.success(request, "This has been deleted.")
        return HttpResponseRedirect(parent_obj_url)
    context = {
        "object": obj
    }
    return render(request, "post/confirm_delete.html", context)

def comment_thread(request, id):
    # obj = get_object_or_404(Comment, id=id)
    obj=Comment.objects.get(id=id)
    try:
        obj=Comment.objects.get(id=id)
    except:
        raise Http404

    content_object = obj.content_object # Post that the comment is on
    content_id = obj.content_object.id

    initial_data = {
            "content_type": obj.content_type,
            "object_id": obj.object_id
    }
    form = CommentForm(request.POST or None, initial=initial_data)
    if form.is_valid():
        c_type = form.cleaned_data.get("content_type")
        content_type = ContentType.objects.get(model=c_type)
        obj_id = form.cleaned_data.get('object_id')
        content_data = form.cleaned_data.get("content")
        parent_obj = None
        try:
            parent_id = int(request.POST.get("parent_id"))
        except:
            parent_id = None

        if parent_id:
            parent_qs = Comment.objects.filter(id=parent_id)
            if parent_qs.exists() and parent_qs.count() == 1:
                parent_obj = parent_qs.first()


        new_comment, created = Comment.objects.get_or_create(
                            user = request.user,
                            content_type= content_type,
                            object_id = obj_id,
                            content = content_data,
                            parent = parent_obj,
                        )

        return HttpResponseRedirect(new_comment.content_object.get_absolute_url())


    context = {
        "comment": obj,
        "form": form,
    }
    return render(request, "post/comment_thread.html", context)


def topic(request,topic):
    templates='post/topic.html'
    # topic_tag= TaggedItem.objects.get(tag_slug__contains=topic).tag
    topic_tag= TaggedItem.objects.filter(tag_slug__contains=topic).values("tag").distinct()

    # getattr(obj, field_name)
    # querysetss=Post.objects.filter(id__in=topic).filter(status='P')
    print topic_tag

    topic_slug= TaggedItem.objects.filter(tag_slug__contains=topic).values('object_id')
    queryset=Post.objects.filter(id__in=topic_slug).filter(status='P')
    print 'topic_slug',topic_slug
    print 'queryset',queryset
    query = request.GET.get("q")
    if query:
		queryset = queryset.filter(
				Q(title__icontains=query)|
				Q(content__icontains=query)|
				Q(user__first_name__icontains=query) |
				Q(user__last_name__icontains=query)
				).distinct()


    paginator = Paginator(queryset, 5) # Show 25 contacts per page
    page_request_var = "page"
    page = request.GET.get(page_request_var)
    try:
        queryset = paginator.page(page)
    except PageNotAnInteger:
        # If page is not an integer, deliver first page.
        queryset = paginator.page(1)
    except EmptyPage:
        # If page is out of range (e.g. 9999), deliver last page of results.
        queryset = paginator.page(paginator.num_pages)



    context = {
        "title": topic_tag,
        "object_list" : queryset,
        "page_request_var":page_request_var,
    }
    return render(request,templates,context)

def CategoryView(request,slug):
    templates='post/category.html'
    # print slug
    # topic_tag= TaggedItem.objects.get(tag_slug__contains=topic).tag
    # cate_slug= Category.objects.filter(slug=slug).values("id").distinct()
    cate_slug= Category.objects.get(slug=slug).id
    print cate_slug
    # getattr(obj, field_name)
    # querysetss=Post.objects.filter(id__in=topic).filter(status='P')
    # print topic_tag

    # cate_slug= Category.objects.filter(slug__contains=slug).values('name')
    queryset=Post.objects.filter(category=int(cate_slug)).filter(status='P')
    # print 'topic_slug',topic_slug
    print 'queryset',queryset
    query = request.GET.get("q")
    if query:
		queryset = queryset.filter(
				Q(title__icontains=query)|
				Q(content__icontains=query)|
				Q(user__first_name__icontains=query) |
				Q(user__last_name__icontains=query)
				).distinct()


    paginator = Paginator(queryset, 5) # Show 25 contacts per page
    page_request_var = "page"
    page = request.GET.get(page_request_var)
    try:
        queryset = paginator.page(page)
    except PageNotAnInteger:
        # If page is not an integer, deliver first page.
        queryset = paginator.page(1)
    except EmptyPage:
        # If page is out of range (e.g. 9999), deliver last page of results.
        queryset = paginator.page(paginator.num_pages)



    context = {
        "title": cate_slug,
        "object_list" : queryset,
        "page_request_var":page_request_var,
    }
    return render(request,templates,context)

class PostLikeRedirect(RedirectView):
    def get_redirect_url(self,*args,**kwargs):
        slug = self.kwargs.get("slug")
        print(slug) #posts/title
        obj = get_object_or_404(Post, slug=slug)
        return obj.get_absolute_url()


class PostLikeToggle(RedirectView):
    def get_redirect_url(self, *args, **kwargs):
        slug = self.kwargs.get("slug")
        print(slug)
        obj = get_object_or_404(Post, slug=slug)
        url_ = obj.get_absolute_url()
        user = self.request.user
        if user.is_authenticated():
            if user in obj.likes.all():
                obj.likes.remove(user)
            else:
                obj.likes.add(user)
                create_action(self.request.user, 'Post like', obj.title)

        return url_


from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import authentication, permissions

class PostLikeAPIToggle(APIView):
    authentication_classes = (authentication.SessionAuthentication,)
    permission_classes = (permissions.IsAuthenticated,)

    def get(self, request, slug=None, format=None):
        # slug = self.kwargs.get("slug")
        obj = get_object_or_404(Post, slug=slug)
        url_ = obj.get_absolute_url()
        user = self.request.user
        updated = False
        liked = False
        if user.is_authenticated():
            if user in obj.likes.all():
                liked = False
                obj.likes.remove(user)
            else:
                liked = True
                obj.likes.add(user)
            updated = True
        data = {
            "updated": updated,
            "liked": liked
        }
        return Response(data)


def post_ranking(request):
    templates='post/ranking.html'
    # get post ranking dictionary
    post_ranking = r.zrange('post_ranking', 0, -1, desc=True)[:10]
    print 'post_ranking',post_ranking,type(post_ranking)
    for obj in post_ranking:
        print 'obj',obj,type(obj)

    post_ranking_ids = [int(id) for id in post_ranking]
    print 'post_ranking_ids',post_ranking_ids
    # get most viewed post
    most_viewed = list(Post.objects.filter(id__in=post_ranking_ids))
    most_viewed.sort(key=lambda x: post_ranking_ids.index(x.id))

    context = {
        "title": 'POST',
        'most_viewed': most_viewed,
    }
    return render(request,templates,context)
