#pragma once

#include <Columns/IColumn_fwd.h>
#include <Processors/Chunk.h>

#include <boost/smart_ptr/intrusive_ptr.hpp>

namespace DB
{
struct SortCursorImpl;
struct SortCursor;
}

namespace DB::detail
{

class SharedChunkAllocator;

/// Allows you refer to the row in the block and hold the block ownership,
///  and thus avoid creating a temporary row object.
/// Do not use std::shared_ptr, since there is no need for a place for `weak_count` and `deleter`;
///  does not use Poco::SharedPtr, since you need to allocate a block and `refcount` in one piece;
///  does not use Poco::AutoPtr, since it does not have a `move` constructor and there are extra checks for nullptr;
/// The reference counter is not atomic, since it is used from one thread.
struct SharedChunk : Chunk
{
    ColumnRawPtrs all_columns;
    ColumnRawPtrs sort_columns;

    /// Used in ReplacingSortedAlgorithm when using skipping final
    MutableColumnPtr replace_final_selection;

    using Chunk::Chunk;
    using Chunk::operator=;

private:
    int refcount = 0;
    size_t position = 0;
    SharedChunkAllocator * allocator = nullptr;

    friend class SharedChunkAllocator;
    friend void intrusive_ptr_add_ref(SharedChunk * ptr);
    friend void intrusive_ptr_release(SharedChunk * ptr);
};

using SharedChunkPtr = boost::intrusive_ptr<detail::SharedChunk>;

/// Custom allocator for shared chunk.
/// It helps to avoid explicit new/delete calls if we know maximum required capacity.
/// Thanks to that, SharedChunk does not own any memory.
/// It improves leaks detection, because memory is allocated only once in constructor.
class SharedChunkAllocator
{
public:
    explicit SharedChunkAllocator(size_t max_chunks)
    {
        if (max_chunks == 0)
            max_chunks = 1;

        chunks.resize(max_chunks);
        free_chunks.reserve(max_chunks);

        for (size_t i = 0; i < max_chunks; ++i)
            free_chunks.push_back(i);
    }

    SharedChunkPtr alloc(Chunk & chunk);

    ~SharedChunkAllocator();

private:
    std::vector<SharedChunk> chunks;
    std::vector<size_t> free_chunks;

    void release(SharedChunk * ptr) noexcept;

    friend void intrusive_ptr_release(SharedChunk * ptr);
};

inline void intrusive_ptr_add_ref(SharedChunk * ptr)
{
    ++ptr->refcount;
}

inline void intrusive_ptr_release(SharedChunk * ptr)
{
    if (0 == --ptr->refcount)
        ptr->allocator->release(ptr);
}

/// This class represents a row in a chunk.
struct RowRef
{
    const IColumn ** sort_columns = nullptr; /// Point to sort_columns from SortCursor or last_chunk_sort_columns.
    size_t num_columns = 0;
    UInt64 row_num = 0;

    UInt64 source_stream_index = 0;

    bool empty() const { return sort_columns == nullptr; }
    void reset() { sort_columns = nullptr; }

    void set(SortCursor & cursor);

    static bool checkEquals(size_t size, const IColumn ** lhs, size_t lhs_row, const IColumn ** rhs, size_t rhs_row);

    static size_t checkEqualsFirstNonEqual(size_t size, size_t offset, const IColumn ** lhs, size_t lhs_row, const IColumn ** rhs, size_t rhs_row);

    size_t firstNonEqualSortColumnsWith(size_t offset, const RowRef & other) const
    {
        return checkEqualsFirstNonEqual(num_columns, offset, sort_columns, row_num, other.sort_columns, other.row_num);
    }

    bool hasEqualSortColumnsWith(const RowRef & other) const
    {
        return checkEquals(num_columns, sort_columns, row_num, other.sort_columns, other.row_num);
    }
};

/// This class also represents a row in a chunk.
/// RowRefWithOwnedChunk hold shared pointer to this chunk, possibly extending its life time.
/// It is needed, for example, in CollapsingTransform, where we need to store first negative row for current sort key.
/// We do not copy data itself, because it may be potentially changed for each row. Performance for `set` is important.
struct RowRefWithOwnedChunk
{
    detail::SharedChunkPtr owned_chunk = nullptr;

    ColumnRawPtrs * all_columns = nullptr;
    ColumnRawPtrs * sort_columns = nullptr;
    UInt64 row_num = 0;

    const SortCursorImpl * current_cursor = nullptr;

    UInt64 source_stream_index = 0;

    void swap(RowRefWithOwnedChunk & other) /// NOLINT(performance-noexcept-swap)
    {
        owned_chunk.swap(other.owned_chunk);
        std::swap(all_columns, other.all_columns);
        std::swap(sort_columns, other.sort_columns);
        std::swap(row_num, other.row_num);
        std::swap(current_cursor, other.current_cursor);
        std::swap(source_stream_index, other.source_stream_index);
    }

    bool empty() const { return owned_chunk == nullptr; }

    void clear()
    {
        owned_chunk.reset();
        all_columns = nullptr;
        sort_columns = nullptr;
        row_num = 0;
        current_cursor = nullptr;
        source_stream_index = 0;
    }

    void set(SortCursor & cursor, SharedChunkPtr chunk);


    size_t firstNonEqualSortColumnsWith(size_t offset, const RowRefWithOwnedChunk & other) const
    {
        return RowRef::checkEqualsFirstNonEqual(sort_columns->size(), offset, sort_columns->data(), row_num, other.sort_columns->data(), other.row_num);
    }

    bool hasEqualSortColumnsWith(const RowRefWithOwnedChunk & other) const
    {
        return RowRef::checkEquals(sort_columns->size(), sort_columns->data(), row_num,
                                   other.sort_columns->data(), other.row_num);
    }
};

}
